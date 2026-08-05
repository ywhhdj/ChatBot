from ..utils import http


async def get_deepseek_balance():
    try:
        res = await http.get(
            f"https://api.deepseek.cn/user/balance",
            headers={
                "Authorization": f"Bearer {config.llm.API_KEY}",
                "Accept": "application/json"
            },
            dtype="json"
        )
        res
    except Exception as e:
        return None