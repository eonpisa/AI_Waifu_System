import json
import os
import websockets
import asyncio
from emotion import expression_presets


VTS_URI = "ws://127.0.0.1:8001"
PLUGIN_NAME = "AI Waifu"
PLUGIN_DEVELOPER = "eonpisa"
TOKEN_FILE = "vts_token.txt"


async def get_token(ws):
    await ws.send(json.dumps({
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": "token",
        "messageType": "AuthenticationTokenRequest",
        "data": {
            "pluginName": PLUGIN_NAME,
            "pluginDeveloper": PLUGIN_DEVELOPER
        }
    }))

    res = json.loads(await ws.recv())
    token = res["data"]["authenticationToken"]

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)

    print("토큰 저장 완료")
    return token


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None

    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


async def auth(ws):
    token = load_token()

    if token is None:
        token = await get_token(ws)

    await ws.send(json.dumps({
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": "auth",
        "messageType": "AuthenticationRequest",
        "data": {
            "pluginName": PLUGIN_NAME,
            "pluginDeveloper": PLUGIN_DEVELOPER,
            "authenticationToken": token
        }
    }))

    res = json.loads(await ws.recv())

    if not res["data"]["authenticated"]:
        print("기존 토큰 인증 실패. 새 토큰 요청.")
        token = await get_token(ws)

        await ws.send(json.dumps({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "auth_retry",
            "messageType": "AuthenticationRequest",
            "data": {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEVELOPER,
                "authenticationToken": token
            }
        }))

        res = json.loads(await ws.recv())

    return res["data"]["authenticated"]


async def apply_expression(emotion, duration=4.0):
    preset = expression_presets.get(emotion, expression_presets["normal"])

    parameter_values = [
        {
            "id": param_id,
            "value": value
        }
        for param_id, value in preset.items()
    ]

    async with websockets.connect(VTS_URI) as ws:
        ok = await auth(ws)

        if not ok:
            print("VTube Studio 인증 실패")
            return

        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < duration:
            await ws.send(json.dumps({
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "expression",
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "parameterValues": parameter_values
                }
            }))

            await ws.recv()
            await asyncio.sleep(0.1)

        print(f"표정 적용 완료: {emotion}")


if __name__ == "__main__":
    import asyncio

    async def test():
        await apply_expression("happy")
        input("표정 확인 중. Enter 누르면 종료: ")

    asyncio.run(test())