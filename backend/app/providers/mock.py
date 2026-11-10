"""Deterministic offline development provider. This is not a language model."""
import hashlib
import json
import math
import re

from app.providers.base import Completion


class MockProvider:
    embedding_model = "mock-hash-v1-1024"

    async def complete(self, messages, *, purpose="generate", json_mode=False, max_tokens=256):
        text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if purpose == "route":
            urgent = any(word in text for word in ("我要自杀", "我想自杀", "现在就去死", "不想活了", "已经吃了很多药", "已经割腕"))
            emotional = any(word in text for word in ("难过", "孤独", "伤心", "想念", "去世", "寂寞", "失眠"))
            recall = any(word in text for word in ("以前", "小时候", "记得", "那年", "西湖"))
            result = {"intent": "emotional_support" if emotional else "reminiscence" if recall else "chat", "risk": "urgent" if urgent else "none", "response_strategy": "controlled_support" if urgent else "listen_then_ask"}
        elif purpose == "extract":
            data = json.loads(text)
            result = {"items": []}
            for message in data.get("messages", []):
                content = message["content"].strip()
                if any(word in content for word in ("如果", "假如", "也许", "可能", "不是", "不喜欢", "不爱", "吗", "？", "?")):
                    continue
                if re.match(r"^我(?:一直|最|很|平时)?(?:喜欢|爱好|爱吃|爱听)", content):
                    result["items"].append({"content": content[:500], "category": "preference", "source_message_ids": [message["id"]]})
                if len(result["items"]) == 3:
                    break
        elif purpose == "review":
            result = {"safe": True, "reason": "ok"}
        elif purpose == "summarize":
            result = {"summary": "以下仅为用户对话的压缩记录，不是已确认家庭事实：" + text[:700]}
        else:
            memories = []
            for message in messages:
                if message["role"] == "system" and message["content"].startswith("CONTEXT_DATA\n"):
                    memories = json.loads(message["content"].split("\n", 1)[1]).get("confirmed_memories", [])
            if any(word in text for word in ("你是谁", "是我女儿", "是我儿子", "真的吗")):
                return Completion("我是这里的 AI 陪伴助手，会参考您设置的说话风格陪您聊聊。我不会代替真实的家人，您也可以随时和信任的人联系。今天想聊些什么？", "mock-development-v1")
            if any(word in text for word in ("记得", "喜欢什么", "爱好")) and memories:
                answer = "您已确认的资料里写着：" + "；".join(m["content"] for m in memories[:2]) + "。这些是您提供的记录；如果现在有变化，可以在记忆里修改。您想从哪件事聊起？"
            elif any(word in text for word in ("记得", "哪年", "叫什么", "生日", "住在哪里")):
                answer = "这件事我还没有可靠的记录，不能替您补上细节。如果您愿意，可以慢慢告诉我；需要长期记住的内容，会先交给您确认。您还记得哪一点？"
            elif any(word in text for word in ("难过", "孤独", "伤心", "想念", "去世", "寂寞")):
                answer = "听起来，今天心里有些不好受。您可以慢慢说，不必急着让自己好起来。我会在这里听，也希望您能和身边信任的人说说。此刻最让您挂心的是什么？"
            elif any(word in text for word in ("以前", "小时候", "那年", "西湖")):
                answer = "这段往事对您似乎很有分量。我不知道当时的具体情景，但很愿意听您亲自讲一讲。您想到那段日子时，最先浮现的是哪个画面？"
            else:
                answer = "您说的我听到了。平常的一点小事，也可以慢慢聊；我会根据您告诉我的内容回应，不清楚的细节会直接说明。今天有没有一件让您特别想说的事？"
            return Completion(answer, "mock-development-v1")
        return Completion(json.dumps(result, ensure_ascii=False), "mock-development-v1")

    async def embed(self, text):
        # Character bigrams provide reproducible local similarity, not semantic AI.
        result = [0.0] * 1024
        for token in list(text) + [text[i:i + 2] for i in range(len(text) - 1)]:
            digest = hashlib.sha256(token.encode()).digest()
            result[int.from_bytes(digest[:4], "big") % 1024] += 1.0
        norm = math.sqrt(sum(v * v for v in result)) or 1.0
        return [v / norm for v in result]

    async def close(self):
        pass
