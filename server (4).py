"""
Space Invaders Co-op Server
Uses aiohttp - stable on Render free tier
"""
import os, json, random, string, time
from aiohttp import web, WSMsgType

PORT = int(os.environ.get("PORT", 10000))
rooms = {}
ws_to_room = {}

def make_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

async def broadcast(code, msg, exclude=None):
    room = rooms.get(code)
    if not room: return
    data = json.dumps(msg)
    for ws in list(room["sockets"]):
        if ws is exclude: continue
        try: await ws.send_str(data)
        except: pass

async def tx(ws, msg):
    try: await ws.send_str(json.dumps(msg))
    except: pass

async def drop(ws):
    code = ws_to_room.pop(id(ws), None)
    if not code: return
    room = rooms.get(code)
    if room:
        pid = room["players"].pop(id(ws), None)
        room["sockets"].discard(ws)
        if pid: await broadcast(code, {"type":"player_left","player_id":pid})
        if not room["sockets"]: rooms.pop(code, None)

async def index(request):
    return web.FileResponse("index.html")

async def wshandler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    try:
        async for raw in ws:
            if raw.type != WSMsgType.TEXT: continue
            try: msg = json.loads(raw.data)
            except: continue
            t = msg.get("type")

            if t == "create_room":
                code = make_code()
                mode = msg.get("mode", "coop")
                max_p = msg.get("max_players", 2)
                rooms[code] = {"sockets":{ws},"players":{id(ws):1},"mode":mode,"max_players":max_p}
                ws_to_room[id(ws)] = code
                await tx(ws, {"type":"room_created","room_code":code,"player_id":1,"mode":mode,"max_players":max_p})

            elif t == "join_room":
                code = msg.get("room_code","").upper().strip()
                room = rooms.get(code)
                if not room:
                    await tx(ws, {"type":"error","msg":"Room not found"})
                elif len(room["sockets"]) >= room["max_players"]:
                    await tx(ws, {"type":"error","msg":"Room is full"})
                else:
                    pid = len(room["sockets"]) + 1
                    room["sockets"].add(ws)
                    room["players"][id(ws)] = pid
                    ws_to_room[id(ws)] = code
                    await tx(ws, {"type":"room_joined","room_code":code,"player_id":pid,"mode":room["mode"],"max_players":room["max_players"]})
                    await broadcast(code, {"type":"player_joined","player_id":pid,"current_count":len(room["sockets"])}, exclude=ws)
                    if len(room["sockets"]) >= room["max_players"]:
                        await broadcast(code, {"type":"start_game","mode":room["mode"],"player_count":len(room["sockets"])})

            elif t == "solo":
                code = make_code()
                rooms[code] = {"sockets":{ws},"players":{id(ws):1},"mode":"solo","max_players":1}
                ws_to_room[id(ws)] = code
                await tx(ws, {"type":"room_created","room_code":code,"player_id":1})
                await tx(ws, {"type":"start_game","mode":"solo","player_count":1})

            elif t == "chat":
                code = ws_to_room.get(id(ws))
                if code:
                    pid = rooms[code]["players"].get(id(ws),1)
                    await broadcast(code,{"type":"chat","player_id":pid,"text":str(msg.get("text",""))[:80],"ts":time.time()})

            else:
                # Relay everything else instantly (bullets, pvp hits, position)
                code = ws_to_room.get(id(ws))
                if code:
                    pid = rooms[code]["players"].get(id(ws),1)
                    msg["from_player"] = pid
                    msg["player_id"] = pid
                    await broadcast(code, msg, exclude=ws)

    finally:
        await drop(ws)
    return ws

app = web.Application()
app.router.add_get("/", index)
app.router.add_get("/index.html", index)
app.router.add_get("/ws", wshandler)

if __name__ == "__main__":
    print(f"Starting on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT, access_log=None)
