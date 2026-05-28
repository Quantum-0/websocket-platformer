import asyncio
import json
import logging
import time
import websockets

logging.basicConfig(level=logging.INFO)

PLAYERS = {}
next_player_id = 1

# Размеры игрока (нужны серверу для проверки попадания удара)
PLAYER_SIZE = 30


async def broadcast(message):
    if PLAYERS:
        payload = json.dumps(message)
        await asyncio.gather(
            *[ws.send(payload) for ws in PLAYERS.keys()],
            return_exceptions=True,
        )


async def game_loop():
    """Игровой цикл сервера (~30 FPS). Рассылает состояние всем."""
    last_regen_time = time.time()

    while True:
        try:
            await asyncio.sleep(1 / 30)
            current_time = time.time()

            # Регенерация +2 HP раз в секунду
            is_regen_tick = False
            if current_time - last_regen_time >= 1.0:
                is_regen_tick = True
                last_regen_time = current_time

            dead_players = []

            for ws, p in list(PLAYERS.items()):
                # Применяем регенерацию
                if is_regen_tick and p["hp"] < 100:
                    p["hp"] = min(100, p["hp"] + 2)

                # Проверяем смерть
                if p["hp"] <= 0:
                    dead_players.append(ws)

            # Удаляем погибших игроков
            for ws in dead_players:
                p_id = PLAYERS[ws]["id"]
                logging.info(f"Игрок {p_id} погиб.")
                try:
                    # Отправляем клиенту причину отключения
                    await ws.send(json.dumps({"type": "game_over"}))
                    await ws.close()
                except Exception:
                    pass
                if ws in PLAYERS:
                    del PLAYERS[ws]
                await broadcast({"type": "remove", "id": p_id})

            if PLAYERS:
                players_data = list(PLAYERS.values())
                await broadcast({"type": "state", "players": players_data})

        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Ошибка в игровом цикле: {e}")


def process_hit(attacker_id, attacker_x, attacker_y):
    """Проверка попадания удара по другим игрокам."""
    # Зона удара: слева и справа на расстояние PLAYER_SIZE
    # То есть x от (attacker_x - PLAYER_SIZE) до (attacker_x + 2 * PLAYER_SIZE)
    # по вертикали проверяем пересечение по Y
    hit_left = attacker_x - PLAYER_SIZE
    hit_right = attacker_x + PLAYER_SIZE * 2

    for ws, p in PLAYERS.items():
        if p["id"] == attacker_id:
            continue

        # Проверка пересечения по горизонтали (зона удара) и вертикали (высота кубика)
        if (
            p["x"] + PLAYER_SIZE > hit_left
            and p["x"] < hit_right
            and p["y"] + PLAYER_SIZE > attacker_y
            and p["y"] < attacker_y + PLAYER_SIZE
        ):
            p["hp"] -= 10
            logging.info(f"Игрок {attacker_id} нанес урон игроку {p['id']}. HP: {p['hp']}/100")


async def handle_client(websocket):
    global next_player_id
    player_id = next_player_id
    next_player_id += 1

    logging.info(f"Игрок {player_id} подключился")

    PLAYERS[websocket] = {
        "id": player_id,
        "x": 100,
        "y": 300,
        "hp": 100,
        "color": f"hsl({(player_id * 60) % 360}, 70%, 50%)",
        "last_attack": 0,  # Таймстамп последней атаки (визуальный эффект)
    }

    try:
        await websocket.send(json.dumps({"type": "init", "id": player_id}))

        async for message in websocket:
            try:
                data = json.loads(message)

                if websocket not in PLAYERS:
                    continue

                if data.get("type") == "move":
                    PLAYERS[websocket]["x"] = data["x"]
                    PLAYERS[websocket]["y"] = data["y"]

                elif data.get("type") == "attack":
                    current_time = time.time()
                    PLAYERS[websocket]["last_attack"] = (
                        current_time  # Запоминаем время удара для анимации
                    )
                    process_hit(
                        player_id,
                        PLAYERS[websocket]["x"],
                        PLAYERS[websocket]["y"],
                    )

            except json.JSONDecodeError:
                pass

    except websockets.ConnectionClosed:
        pass
    finally:
        if websocket in PLAYERS:
            del PLAYERS[websocket]
            logging.info(f"Игрок {player_id} отключился")
            await broadcast({"type": "remove", "id": player_id})


async def main():
    asyncio.create_task(game_loop())
    async with websockets.serve(handle_client, "0.0.0.0", 8001):
        logging.info("Сервер запущен на ws://localhost:8001")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
