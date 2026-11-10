using AALC.Core.Automation;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Automation;
using AALC.Runtime.Mail;
using System.Text.Json;

namespace AALC.Runtime.Mirror;

public interface IMirrorMapReader
{
    MirrorMapSnapshot Read(PixelFrame frame, PixelPoint bus, CancellationToken cancellationToken);
}

public enum MirrorRouteOutcome { Entered, NotMap, Failed }
public sealed record MirrorRouteResult(MirrorRouteOutcome Outcome, string Reason, MirrorNodeKind? Node = null);

public sealed class MirrorRouteFlow(IGameSession session, IMirrorMapReader mapReader)
{
    private sealed record RouteStep(MirrorNodeKind Kind, double DeltaY);
    private readonly Queue<RouteStep> cachedRoute = new();
    private bool awaitingEntry;
    private bool postShop;

    public void NotifyShopExited() => postShop = true;

    public void ResetForFloor()
    {
        cachedRoute.Clear();
        awaitingEntry = false;
        postShop = false;
    }

    public const string Legend = "mirror/road_in_mir/legend_assets.png";
    public const string Bus = "mirror/mybus_default_distance.png";
    public const string Enter = "mirror/road_in_mir/enter_assets.png";
    private static readonly string[] Destinations = ["teams/identify_assets.png", "battle/normal_to_battle_assets.png",
        "battle/chaim_to_battle_assets.png", "battle/more_information_assets.png",
        "battle/turn_assets.png", "battle/pause_assets.png", "mirror/shop/shop_coins_assets.png",
        "mirror/theme_pack/theme_pack_features.png", "mirror/theme_pack/feature_theme_pack_assets.png",
        "mirror/road_in_mir/ego_gift_get_confirm_assets.png",
        "mirror/road_in_mir/acquire_ego_gift_select_assets.png", MirrorRewardFlow.Cards, MirrorRewardFlow.Gift,
        MirrorRewardFlow.GiftBox, MirrorSettlementFlow.Clear,
        MirrorSettlementFlow.Complete, MirrorSettlementFlow.Claim];
    public static readonly ImageQuery[] Queries = [new(Legend), new(Bus, Search: SearchMode.Aggressive),
        new(Enter), new("base/waiting_assets.png"), .. Destinations.Select(asset => new ImageQuery(asset)),
        .. MirrorEventFlow.PageQueries];

    public async Task<MirrorRouteResult> AdvanceAsync(MirrorRouteOptions options, CancellationToken ct)
    {
        var frame = await session.ObserveAsync(Queries, ct);
        if (IsDestination(frame))
        {
            postShop = false;
            return awaitingEntry ? await EnterAndConfirmAsync(frame, null, ct) : new(MirrorRouteOutcome.NotMap, "not-map");
        }
        if (frame.Find(Enter) is not null)
        {
            postShop = false;
            return await EnterAndConfirmAsync(frame, null, ct);
        }
        if (frame.Find(Legend) is null) return new(MirrorRouteOutcome.NotMap, "not-map");
        if (postShop && cachedRoute.Count == 0)
        {
            postShop = false;
            session.Report("mirror.route.post-shop", "商店离店后尝试W导航，并确认新页面反馈");
            frame = await NavigateByKeyAsync(frame, GameKey.W, "mirror.route.post-shop-next", ct);
            if (frame.Find(Enter) is not null || IsDestination(frame))
                return await EnterAndConfirmAsync(frame, null, ct);
            session.Report("mirror.route.post-shop-miss", "W导航未确认选中节点，重新识别地图");
            if (frame.Find(Legend) is null) return new(MirrorRouteOutcome.NotMap, "post-shop-page-unconfirmed");
        }
        postShop = false;
        if (frame.Find("base/waiting_assets.png") is null && cachedRoute.TryPeek(out var step))
        {
            session.Report("mirror.route.cache-hit", $"复用路线缓存：{Name(step.Kind)}");
            awaitingEntry = true;
            var direction = step.DeltaY < -100 ? GameKey.Up : step.DeltaY > 100 ? GameKey.Down : GameKey.Right;
            frame = await NavigateByKeyAsync(frame, direction, "mirror.route.select-direction", ct);
            if (frame.Find(Legend) is null || frame.Find(Enter) is not null || IsDestination(frame)
                || frame.Find("base/waiting_assets.png") is not null)
                return await EnterAndConfirmAsync(frame, step.Kind, ct);
            cachedRoute.Clear();
            awaitingEntry = false;
            session.Report("mirror.route.cache-miss", "缓存方向键未确认选中节点，按新地图重新扫描");
        }
        var scan = new MirrorMapScan();
        PixelPoint? beforePan = null;
        var missingRechecks = 0;
        for (var scout = 0; scout <= 4;)
        {
            ct.ThrowIfCancellationRequested();
            // 读档后的地图会淡出再淡入，给够一次过渡时间再判定巴士丢失。
            for (var wait = 0; wait < 8 && frame.Find(Bus) is null; wait++)
            {
                await session.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
                frame = await session.ObserveControlsAsync(Queries, ct);
            }
            if (frame.Find(Bus) is null)
                return Failed("bus-not-visible", "地图未识别到巴士，停止寻路");
            var stable = await StableMapAsync(frame, session.Elapsed + TimeSpan.FromSeconds(2), ct);
            if (stable is null) return Failed("map-moving", "地图持续移动，停止选点");
            frame = stable;
            if (IsDestination(frame)) return new(MirrorRouteOutcome.NotMap, "destination-visible");
            if (frame.Find(Enter) is not null) return await EnterAndConfirmAsync(frame, null, ct);
            if (frame.Find(Legend) is null) return Failed("map-lost-before-selection", "选点前未确认地图页面");
            if (frame.Find(Bus) is not { } bus) return Failed("bus-not-visible", "地图未识别到巴士，停止寻路");
            var map = ReadMap(frame, bus.Center, ct);
            var added = scan.Add(map);
            session.Report("mirror.route.scan", JsonSerializer.Serialize(new
            {
                origin = scan.Observations[0].Frame, frame = map.Frame, added,
                nodes = scan.Nodes.Select(node => new { node.Id, node.Kind, relative = node.Center,
                    disputed = scan.Disputed.Contains(node.Id), sources = scan.Sources(node.Id) }),
                connections = scan.Connections.Select(edge => new { edge.From, edge.To, sources = scan.Sources(edge) })
            }));
            var plan = scan.Choose(options);
            var vertex = plan?.Nodes[0];
            var next = vertex is null ? null : scan.Confirm(vertex, map);
            if (vertex is not null && next is null
                && MirrorMapViewport.Contains(frame.Identity, MirrorMapViewport.ProjectForCamera(vertex, map)))
            {
                if (missingRechecks++ < 2)
                {
                    session.Report("mirror.route.scan-recheck", "首步在当前视野中暂未识别，取得新帧复核");
                    frame = await session.ObserveAsync(Queries, ct);
                    continue;
                }
                return Failed("first-step-unconfirmed", "多次新观察仍未确认首步节点与连接，停止选点");
            }
            missingRechecks = 0;
            var selectable = next is not null && MirrorMapViewport.Contains(frame.Identity, next.Bounds);
            var moved = beforePan is null || Math.Abs(bus.Center.X - beforePan.Value.X) > 4 * frame.Scale
                || Math.Abs(bus.Center.Y - beforePan.Value.Y) > 4 * frame.Scale;
            var frontier = scan.Nodes.Where(node => !scan.Disputed.Contains(node.Id)).MaxBy(node => node.Center.X);
            var probeRight = frontier is not null && frontier.Kind != MirrorNodeKind.BossBattle
                && !scan.Connections.Any(edge => edge.From == frontier.Id)
                && scan.Sources(frontier.Id).Any(source => source.Frame == frame.Identity);
            var shift = MirrorMapViewport.Shift(map, bus.Bounds,
                vertex is null ? null : next?.Bounds ?? MirrorMapViewport.ProjectForCamera(vertex, map), probeRight);
            if (shift is null && scout == 0 && map.Nodes.Count == 0)
            {
                var vertical = Math.Clamp(frame.Identity.Height / 2 - bus.Center.Y,
                    -(int)(220 * frame.Scale), (int)(220 * frame.Scale));
                if (Math.Abs(vertical) >= 32 * frame.Scale) shift = new(0, vertical);
            }
            if (next is not null && selectable && (MirrorRoutePlanner.IsLocalBossCandidate(plan!.Nodes[^1], scan.Connections) || shift is null || scout == 4
                || !moved || scout > 0 && added == 0))
            {
                session.Report("mirror.route.scan-complete", $"当前局部视野可用：{scan.Nodes.Count}节点/{scan.Connections.Count}条实测连接，补扫{scout}次");
                session.Report("mirror.route.select", $"选择下一节点：{Name(next.Kind)}");
                CachePlan(plan!);
                await session.ClickAsync(frame, next.Center, "mirror.route.select-node", ct);
                await session.DelayAsync(TimeSpan.FromMilliseconds(750), ct);
                frame = await session.ObserveAsync(Queries, ct);
                return await EnterAndConfirmAsync(frame, next.Kind, ct, options, 4 - scout);
            }
            if (scout == 4 || shift is null || !moved)
            {
                if (!moved) return Failed("camera-no-progress", "地图补扫未取得实际位移，停止选点");
                if (vertex is not null) return Failed(next is null ? "first-step-unconfirmed" : "node-outside-map",
                    "当前帧未确认可操作的首步节点与连接，停止选点");
                if (ModelBlind(scan)) return await KeyboardFallbackAsync(frame, ct);
                return Failed("no-confirmed-connection", "未识别到巴士通往下一节点的连接，停止寻路");
            }
            beforePan = bus.Center;
            session.Report("mirror.route.scan-pan", $"补扫地图：巴士({bus.Center.X},{bus.Center.Y})，平移({shift.Value.X},{shift.Value.Y})，"
                + $"当前{scan.Nodes.Count}节点/{scan.Connections.Count}条实测连接");
            await DragCameraAsync(frame, shift.Value.X, shift.Value.Y, ct);
            scout++;
            frame = await session.ObserveAsync(Queries, ct);
            if (IsDestination(frame)) return new(MirrorRouteOutcome.NotMap, "destination-visible");
            if (frame.Find(Enter) is not null) return await EnterAndConfirmAsync(frame, null, ct);
            if (frame.Find(Legend) is null) return Failed("map-lost-after-camera", "视角调整后未确认地图页面");
        }
        if (ModelBlind(scan)) return await KeyboardFallbackAsync(frame, ct);
        return Failed("no-confirmed-connection", "未识别到巴士通往下一节点的连接，停止寻路");
    }

    // 节点清晰但连接不明时仍停止而不猜方向；只有模型整体看不懂地图时才兜底。
    private static bool ModelBlind(MirrorMapScan scan) => scan.Nodes.All(node => node.Score < 0.5);

    /// <summary>
    /// 地图模型整体失效时（如“由子弹画下的句点”的统一问号节点，只给出零星低分框）沿用旧版简单键盘寻路：
    /// 依次尝试中、上、下方向键并回车，只有出现进入按钮或节点页面才算选中。
    /// </summary>
    private async Task<MirrorRouteResult> KeyboardFallbackAsync(GameFrame frame, CancellationToken ct)
    {
        session.Report("mirror.route.keyboard-fallback", "地图识别未得到可达节点，改用方向键依次尝试");
        cachedRoute.Clear();
        awaitingEntry = false;
        foreach (var key in new[] { GameKey.Right, GameKey.Up, GameKey.Down })
        {
            if (frame.Find(Legend) is null) break;
            frame = await NavigateByKeyAsync(frame, key, "mirror.route.fallback-direction", ct);
            if (frame.Find(Enter) is not null || IsDestination(frame) || frame.Find(Legend) is null
                || frame.Find("base/waiting_assets.png") is not null)
                return await EnterAndConfirmAsync(frame, null, ct);
        }
        return Failed("no-confirmed-connection", "未识别到节点，方向键也未选中节点，停止寻路");
    }

    private async Task<MirrorRouteResult> EnterAndConfirmAsync(GameFrame frame, MirrorNodeKind? node, CancellationToken ct,
        MirrorRouteOptions? options = null, int cameraBudget = 0)
    {
        var entered = 0;
        TimeSpan? lastEntryAt = null;
        var unknown = 0;
        var mapFrames = 0;
        var reselections = 0;
        MirrorMapScan? scan = null;
        var beginning = session.Elapsed;
        while (session.Elapsed - beginning < TimeSpan.FromSeconds(30))
        {
            ct.ThrowIfCancellationRequested();
            if (await DestinationConfirmedAsync(frame, ct))
            {
                if (awaitingEntry && cachedRoute.TryDequeue(out var consumed)) node ??= consumed.Kind;
                else cachedRoute.Clear();
                awaitingEntry = false;
                session.Report("mirror.route.entered", "已确认节点页面，交回镜牢流程");
                return new(MirrorRouteOutcome.Entered, "destination-confirmed", node);
            }
            mapFrames = entered == 0 && frame.Find(Legend) is not null && frame.Find(Bus) is not null
                && frame.Find(Enter) is null && frame.Find("base/waiting_assets.png") is null ? mapFrames + 1 : 0;
            if (options is not null && mapFrames >= 3)
            {
                if (reselections >= 3) break;
                var stable = await StableMapAsync(frame, beginning + TimeSpan.FromSeconds(30), ct);
                if (session.Elapsed - beginning >= TimeSpan.FromSeconds(30)) break;
                if (stable is null) return Failed("map-moving", "地图持续移动，停止重新选点");
                frame = stable;
                mapFrames = 0;
                if (IsDestination(frame) || frame.Find(Enter) is not null || frame.Find(Legend) is null
                    || frame.Find("base/waiting_assets.png") is not null) continue;
                if (frame.Find(Bus) is not { } bus) return Failed("bus-not-visible", "地图未识别到巴士，停止寻路");
                // 与旧版一致：下一节点点不开时点巴士，战斗中途退出后要先重新进入巴士所在节点。
                if (reselections == 1)
                {
                    reselections++;
                    session.Report("mirror.route.retry-bus", "下一节点无法选中，改为重新进入巴士所在节点");
                    await session.ClickAsync(frame, bus.Center, "mirror.route.select-bus", ct);
                    await session.DelayAsync(TimeSpan.FromMilliseconds(750), ct);
                    frame = await session.ObserveAsync(Queries, ct);
                    unknown = 0;
                    continue;
                }
                var map = ReadMap(frame, bus.Center, ct);
                scan ??= new();
                scan.Add(map);
                var plan = scan.Choose(options);
                if (plan is null) return Failed("no-confirmed-connection", "重新选点未识别到可达节点，停止寻路");
                var next = scan.Confirm(plan.Nodes[0], map);
                if (next is null || !MirrorMapViewport.Contains(frame.Identity, next.Bounds))
                {
                    if (cameraBudget == 0) return Failed("node-outside-map", "当前帧未确认可操作的首步节点，停止选点");
                    var shift = MirrorMapViewport.Shift(map, bus.Bounds,
                        next?.Bounds ?? MirrorMapViewport.ProjectForCamera(plan.Nodes[0], map));
                    if (shift is null) return Failed("first-step-unconfirmed", "当前帧未确认首步节点与连接，停止选点");
                    await DragCameraAsync(frame, shift.Value.X, shift.Value.Y, ct);
                    cameraBudget--;
                    frame = await session.ObserveAsync(Queries, ct);
                    unknown = 0;
                    continue;
                }
                node = next.Kind;
                CachePlan(plan);
                reselections++;
                session.Report("mirror.route.retry", "地图仍未出现进入按钮，重新识别后选择节点");
                await session.ClickAsync(frame, next.Center, "mirror.route.select-node", ct);
                scan = null;
                await session.DelayAsync(TimeSpan.FromMilliseconds(750), ct);
                frame = await session.ObserveAsync(Queries, ct);
                unknown = 0;
                continue;
            }
            if (frame.Find(Enter) is { } enter)
            {
                unknown = 0;
                if (entered < 3 && (lastEntryAt is null || session.Elapsed - lastEntryAt.Value >= TimeSpan.FromMilliseconds(1250)))
                {
                    session.Report("mirror.route.enter", "进入已选择的节点");
                    await session.ClickAsync(frame, enter.Center, "mirror.route.enter-node", ct);
                    lastEntryAt = session.Elapsed;
                    entered++;
                }
            }
            else if (frame.Find("base/waiting_assets.png") is null && ++unknown > 8) break;
            var remaining = TimeSpan.FromSeconds(30) - (session.Elapsed - beginning);
            if (remaining <= TimeSpan.Zero) break;
            await session.DelayAsync(remaining < TimeSpan.FromMilliseconds(500) ? remaining : TimeSpan.FromMilliseconds(500), ct);
            frame = await session.ObserveAsync(Queries, ct);
        }
        return Failed("destination-unconfirmed", "选择节点后未确认编队、战斗、事件、商店或奖励页面");
    }

    private void CachePlan(MirrorRoutePlan plan)
    {
        cachedRoute.Clear();
        var previous = new PixelPoint(0, 0);
        foreach (var node in plan.Nodes)
        {
            cachedRoute.Enqueue(new(node.Kind, node.Center.Y - previous.Y));
            previous = node.Center;
        }
        awaitingEntry = true;
    }

    private async Task<GameFrame> NavigateByKeyAsync(GameFrame frame, GameKey key, string rule, CancellationToken ct)
    {
        await session.KeyAsync(frame, key, rule, ct);
        await session.DelayAsync(TimeSpan.FromMilliseconds(500), ct);
        frame = await session.ObserveAsync(Queries, ct);
        if (frame.Find(Enter) is not null || IsDestination(frame) || frame.Find(Legend) is null
            || frame.Find("base/waiting_assets.png") is not null) return frame;
        await session.KeyAsync(frame, GameKey.Enter, "mirror.route.confirm-selection", ct);
        await session.DelayAsync(TimeSpan.FromMilliseconds(1250), ct);
        return await session.ObserveAsync(Queries, ct);
    }

    private async Task DragCameraAsync(GameFrame frame, double dx, double dy, CancellationToken ct)
    {
        // 游戏吃掉拖动起始约 13 像素（720p 实测 10～16），沿拖动方向补偿，避免差几像素再补拖一次。
        var length = Math.Sqrt(dx * dx + dy * dy);
        var compensation = length > 0 ? (length + 26 * frame.Scale) / length : 1;
        var from = new PixelPoint(frame.Identity.Width / 2, frame.Identity.Height / 2);
        var to = new PixelPoint(Math.Clamp(from.X + (int)Math.Round(dx * compensation), 1, frame.Identity.Width - 1),
            Math.Clamp(from.Y + (int)Math.Round(dy * compensation), (int)(frame.Identity.Height * 0.2), (int)(frame.Identity.Height * 0.8)));
        session.Report("mirror.route.camera", "调整地图视角后重新识别");
        await session.DragAsync(frame, from, to, TimeSpan.FromMilliseconds(200), "mirror.route.align-camera", ct);
        await session.DelayAsync(TimeSpan.FromMilliseconds(300), ct);
    }

    private async Task<GameFrame?> StableMapAsync(GameFrame frame, TimeSpan deadline, CancellationToken ct)
    {
        var previous = frame.Find(Bus)?.Center;
        var stable = 0;
        for (var poll = 0; poll < 12 && session.Elapsed < deadline; poll++)
        {
            await session.DelayAsync(TimeSpan.FromMilliseconds(Math.Min(120, (deadline - session.Elapsed).TotalMilliseconds)), ct);
            frame = await session.ObserveControlsAsync(Queries, ct);
            if (IsDestination(frame) || frame.Find(Enter) is not null) return frame;
            if (frame.Find(Legend) is null || frame.Find(Bus) is not { } bus)
            {
                previous = null;
                stable = 0;
                continue;
            }
            stable = frame.Find("base/waiting_assets.png") is null && previous is { } point
                && Math.Abs(bus.Center.X - point.X) <= 4 * frame.Scale
                && Math.Abs(bus.Center.Y - point.Y) <= 4 * frame.Scale ? stable + 1 : 0;
            if (stable >= 2) return frame;
            previous = bus.Center;
        }
        return null;
    }

    private MirrorMapSnapshot ReadMap(GameFrame frame, PixelPoint bus, CancellationToken ct)
    {
        session.Report("mirror.route.read", "识别当前可见节点与连接");
        var map = mapReader.Read(frame.Pixels, bus, ct);
        if (map.Frame != frame.Identity) throw new InvalidDataException("地图识别结果与输入帧不一致");
        session.Report("mirror.route.map", JsonSerializer.Serialize(map));
        return map;
    }

    private async ValueTask<bool> DestinationConfirmedAsync(GameFrame frame, CancellationToken ct)
    {
        if (IsDestination(frame)) return true;
        if (frame.Find(Legend) is not null || frame.Find("base/waiting_assets.png") is not null) return false;
        var text = await session.ReadTextAsync(frame, ct);
        return BattleEvents.HasNarration(frame, text);
    }

    private static bool IsDestination(GameFrame frame) => MirrorEventFlow.HasEventPageEvidence(frame)
        || Destinations.Any(asset => frame.Find(asset) is not null
        && (frame.Find(Legend) is null || asset is not ("battle/more_information_assets.png"
            or "battle/turn_assets.png" or "battle/pause_assets.png")));
    private MirrorRouteResult Failed(string reason, string message)
    {
        session.Report("mirror.route.failed", message);
        return new(MirrorRouteOutcome.Failed, reason);
    }
    private static string Name(MirrorNodeKind kind) => kind switch
    {
        MirrorNodeKind.Battle => "普通战斗", MirrorNodeKind.BossBattle => "首领战斗", MirrorNodeKind.Event => "事件",
        MirrorNodeKind.HardBattle => "集中战斗", MirrorNodeKind.EliteBattle => "精锐战斗", MirrorNodeKind.Shop => "商店",
        MirrorNodeKind.Unknown => "未分类节点",
        _ => "异想体战斗"
    };
}
