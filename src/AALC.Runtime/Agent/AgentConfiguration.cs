using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using AALC.Core.Features.Daily;
using AALC.Core.Features.Mirror;
using AALC.Runtime.Configuration;

namespace AALC.Runtime.Agent;

public static class AgentConfiguration
{
    private static readonly JsonSerializerOptions Strict = new() { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow };

    public static string Revision(DesktopSettings settings) => Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(settings)));

    public static DesktopSettings Patch(DesktopSettings settings, JsonElement patch)
    {
        if (patch.ValueKind != JsonValueKind.Object) throw new ArgumentException("配置 patch 须为 JSON 对象");
        var target = JsonSerializer.SerializeToNode(settings)!.AsObject();
        Merge(target, JsonNode.Parse(patch.GetRawText())!.AsObject());
        var result = target.Deserialize<DesktopSettings>(Strict) ?? throw new InvalidDataException("配置为空");
        DailyPlan.Validate(result.Daily ?? new());
        MirrorPlan.ValidateConfiguration(result.Mirror ?? new());
        if (result.GameLanguage is not ("zh_cn" or "en") || result.GameTheme is not ("default" or "dark"))
            throw new ArgumentException("游戏语言或主题无效");
        if (result.App?.StartPage is { } page && page is not ("launch" or "daily" or "mirror" or "monitor"))
            throw new ArgumentException("启动页面无效");
        return result;
    }

    private static void Merge(JsonObject target, JsonObject patch)
    {
        foreach (var pair in patch)
        {
            if (pair.Value is JsonObject child && target[pair.Key] is JsonObject current) Merge(current, child);
            else target[pair.Key] = pair.Value?.DeepClone();
        }
    }
}
