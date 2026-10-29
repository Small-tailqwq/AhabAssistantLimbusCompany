using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;

namespace AALC.Runtime.Tools;

public sealed record TutorialSavePatch(string Encrypted, int ModifiedModels, int AddedModels);

public static class TutorialSave
{
    public static TutorialSavePatch Patch(string encrypted, byte[] key, byte[] iv, bool disabled)
    {
        using var aes = Aes.Create();
        aes.Key = key;
        var plaintext = aes.DecryptCbc(Convert.FromBase64String(encrypted.Trim().TrimStart('\uFEFF')), iv);
        var data = JsonNode.Parse(plaintext)?.AsObject() ?? throw new InvalidDataException("存档为空。");
        var dictionary = data["_stringDic"]?.AsObject() ?? throw new InvalidDataException("存档缺少 _stringDic。");
        var keys = dictionary["keys"]?.AsArray() ?? throw new InvalidDataException("存档缺少数据模型名称。");
        var values = dictionary["values"]?.AsArray() ?? throw new InvalidDataException("存档缺少数据模型内容。");
        if (keys.Count != values.Count) throw new InvalidDataException("存档数据模型名称与内容数量不同。");
        var existing = new HashSet<string>();
        var modified = 0;
        for (var i = 0; i < keys.Count; i++)
        {
            var name = keys[i]!.GetValue<string>();
            existing.Add(name);
            if (name is not ("LocalSave.UserLocalTutorialSaveModel" or "UserLocalFormationDataModel"
                or "UserLocalMirrorDungeonRedDotModel" or "UserLocalCheckBoxSaveModel"
                or "UserLocalDialogResultSaveModel" or "UserLocalNoticeRedDotModel")) continue;
            var original = values[i]!.GetValue<string>();
            var model = JsonNode.Parse(original)!.AsObject();
            var before = model.ToJsonString();
            switch (name)
            {
                case "LocalSave.UserLocalTutorialSaveModel" when model["tutorialDic"] is JsonObject tutorials:
                    var tutorialIds = (tutorials["keys"]?.AsArray() ?? []).Select(item => item!.GetValue<int>())
                        .Union(Enumerable.Range(1, 23)).ToArray();
                    tutorials["keys"] = new JsonArray(tutorialIds.Select(value => JsonValue.Create(value) as JsonNode).ToArray());
                    tutorials["values"] = new JsonArray(tutorialIds.Select(_ => JsonValue.Create(disabled) as JsonNode).ToArray());
                    break;
                case "UserLocalFormationDataModel":
                    foreach (var field in new[] { "_isParticipation7TutorialOccured", "_isStoryDungeon4Opened", "_isRailwayDungeonLine2LastNodeEnterFirst" })
                        if (model.ContainsKey(field)) model[field] = disabled;
                    break;
                case "UserLocalMirrorDungeonRedDotModel":
                    model["_isParticipation7TutorialOccured"] = disabled;
                    break;
                case "UserLocalCheckBoxSaveModel":
                    foreach (var item in model["_checkBoxDataList"]?.AsArray() ?? []) item!["isChecked"] = disabled;
                    break;
                case "UserLocalDialogResultSaveModel":
                    foreach (var item in model["_dataList"]?.AsArray() ?? [])
                    { item!["isDoNotShowAgain"] = disabled; item["isConfirmed"] = disabled; }
                    break;
                case "UserLocalNoticeRedDotModel" when disabled:
                    var notices = (model["idList"]?.AsArray() ?? []).Select(item => item!.GetValue<int>());
                    model["idList"] = new JsonArray(notices.Union(Enumerable.Range(200001, 699)).Order()
                        .Select(value => JsonValue.Create(value) as JsonNode).ToArray());
                    break;
            }
            var patched = model.ToJsonString();
            if (before == patched) continue;
            values[i] = patched;
            modified++;
        }
        var added = 0;
        if (disabled)
        {
            Dictionary<string, string> defaults = new()
            {
                ["UserLocalFormationDataModel"] = """{"_formerNormalBattleTotalCount":0,"_formerStoryDungeonBattleTotalCount":0,"_isParticipation7TutorialOccured":true,"_isStoryDungeon4Opened":true,"_isRailwayDungeonLine2LastNodeEnterFirst":true}""",
                ["UserLocalMirrorDungeonRedDotModel"] = """{"idList":[],"_isMirrorDungeonOpenedRedDotExist":false,"_isParticipation7TutorialOccured":true,"_lastDifficulty":0,"_participation":{"_recentPersonalityParticipatedOrder":[],"_recentAllAliveCharacterParticipatedOrder":[],"_dungeonStartDate":"2026-01-01T00:00:00.000Z"}}""",
                ["UserLocalNoticeRedDotModel"] = new JsonObject { ["idList"] = new JsonArray(Enumerable.Range(200001, 699).Select(value => JsonValue.Create(value) as JsonNode).ToArray()), ["isChanged"] = false }.ToJsonString(),
                ["UserLocalDialogResultSaveModel"] = """{"idList":[],"_dataList":[],"isChanged":false}"""
            };
            foreach (var (name, content) in defaults)
            {
                if (existing.Contains(name)) continue;
                keys.Add(name);
                values.Add(content);
                added++;
            }
        }
        var output = modified == 0 && added == 0 ? encrypted
            : Convert.ToBase64String(aes.EncryptCbc(Encoding.UTF8.GetBytes(data.ToJsonString()), iv));
        return new(output, modified, added);
    }
}
