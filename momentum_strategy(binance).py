#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import numpy as np
import json
import time
from binance.client import Client
from binance.enums import *
from collections import deque
import requests





# In[2]:


# API 키 설정
API_KEY = '9lUtP1Cs2NqkPL84OmBnAS1q2qHRyBS62hg2IpfWpEftYD5roPZJIGFVVgAbwFDm'
API_SECRET = 'eYbmAiG7d5wK9d9pSDJ52DBinurwIe6LeElJ7Wui8HmfdgziE9ocgGrYzYK6XoxS'

#텔레그램 연결
TOKEN  = "7967036104:AAFyBIclONMQrspBfTmym35-C8O9KlDgUxA"  # 여기에 너의 봇 토큰 입력
CHAT_ID  = "5034436727"

# Binance 클라이언트 생성
client = Client(API_KEY, API_SECRET, testnet=False)


# In[ ]:


tech_dict = dict()
leverage = 5
interval = "5m"  # 1분봉
entry_price = dict()
max_period = 288
open_list = deque(maxlen=max_period)
high_list = deque(maxlen=max_period)
low_list = deque(maxlen=max_period)
close_list = deque(maxlen=max_period)

symbols = ['btcusdt', 'ethusdt', 'xrpusdt','solusdt','bnbusdt','adausdt', 'trxusdt', 'hbarusdt', 'linkusdt']
coin_data = {symbol.upper(): {"open": [], "high": [], "low": [], "close": [], "volume": []} for symbol in symbols}

symbol_precisions = {
    'btcusdt': 3,
    'ethusdt': 3,
    'xrpusdt': 0,
    'solusdt': 0,
    'bnbusdt': 2,
    'adausdt': 0,
    'dogeusdt': 0,
    'trxusdt': 0,
    'hbarusdt': 0,
    'linkusdt': 2
}

# API 키 설정
API_KEY = '9lUtP1Cs2NqkPL84OmBnAS1q2qHRyBS62hg2IpfWpEftYD5roPZJIGFVVgAbwFDm'
API_SECRET = 'eYbmAiG7d5wK9d9pSDJ52DBinurwIe6LeElJ7Wui8HmfdgziE9ocgGrYzYK6XoxS'

# Binance 클라이언트 생성
client = Client(API_KEY, API_SECRET, testnet=False)

SERVER_TIME_OFFSET = 0
LAST_SYNCED_TIME = 0

def sync_time_offset():
    global SERVER_TIME_OFFSET, LAST_SYNCED_TIME
    try:
        server_time = requests.get('https://fapi.binance.com/fapi/v1/time').json()['serverTime']
        local_time = int(time.time() * 1000)
        SERVER_TIME_OFFSET = server_time - local_time
        LAST_SYNCED_TIME = time.time()
    except:
        print("⚠️ 서버 시간 동기화 실패")

def safe_timestamp():
    """오차 보정된 안전한 timestamp 반환"""
    global LAST_SYNCED_TIME
    if time.time() - LAST_SYNCED_TIME > 10:  # 10초마다 갱신
        sync_time_offset()
    return int(time.time() * 1000 + SERVER_TIME_OFFSET)

def get_position_info(symbol):
    """현재 심볼의 포지션 정보 가져오기"""
    positions = client.futures_position_information()
    for position in positions:
        if position["symbol"] == symbol.upper():
            position_size = float(position["positionAmt"])
            return position_size
    return 0

def close_position(symbol):
    """현재 포지션을 시장가로 청산"""
    position_size = get_position_info(symbol)
    if position_size == 0:
        print(f"{symbol}에 대한 열린 포지션이 없습니다.")
        return

    # 포지션 방향 확인
    side = SIDE_SELL if position_size > 0 else SIDE_BUY
    position_size = abs(position_size)  # 양수로 변환

    try:
        order = client.futures_create_order(
            symbol=symbol.upper(),
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=position_size
        )
        print(f"포지션 청산 성공: {order}")
    except Exception as e:
        print(f"포지션 청산 실패: {e}")

def set_leverage(symbol, leverage):
    """레버리지 설정"""
    try:
        response = client.futures_change_leverage(symbol=symbol.upper(), leverage=leverage, timestamp=safe_timestamp(), recvWindow=5000)
        #print(f"레버리지 설정 성공: {response}")
    except Exception as e:
        print(f"레버리지 설정 실패: {e}")

def get_market_price(symbol):
    """현재 시장가 가져오기"""
    ticker = client.futures_symbol_ticker(symbol=symbol.upper())
    return float(ticker["price"])

def calculate_position_size(position_value, market_price, symbol):
    """포지션 사이즈 계산 (코인별 precision 적용)"""
    precision = symbol_precisions.get(symbol.lower(), 2)  # 기본값 2
    size = position_value / market_price
    return round(size, precision)

def place_market_order(symbol, position_size, side):
    """시장가 주문 실행"""
    try:
        order = client.futures_create_order(
            symbol=symbol.upper(),
            side=side,
            type= ORDER_TYPE_MARKET,
            quantity=position_size,
            timestamp=safe_timestamp()
        )
        print("Order executed:", order)
        return True
    except Exception as e:
        print("Error placing order:", e)
        return False
    
def get_tick_size(symbol):
    """심볼의 tickSize (호가 단위) 가져오기"""
    exchange_info = client.futures_exchange_info()
    for s in exchange_info['symbols']:
        if s['symbol'] == symbol.upper():
            for f in s['filters']:
                if f['filterType'] == 'PRICE_FILTER':
                    return float(f['tickSize'])
    return 0.01  # 기본값 (예외 처리용)

def round_price_to_tick(price, tick_size):
    """tickSize에 맞게 가격 반올림"""
    return round(round(price / tick_size) * tick_size, 8)


def place_limit_order_with_auto_cancel(symbol, position_size, side, timeout=60):
    """
    최우선 호가 기준 지정가 주문 + 5분 후 미체결시 자동 취소
    """
    try:
        # 호가 정보
        order_book = client.futures_order_book(symbol=symbol.upper(), limit=5)
        tick_size = get_tick_size(symbol)

        if side == SIDE_BUY:
            best_price = float(order_book['bids'][0][0])
        elif side == SIDE_SELL:
            best_price = float(order_book['asks'][0][0])
        else:
            print("잘못된 주문 방향입니다.")
            return 0

        price = round_price_to_tick(best_price, tick_size)

        # 지정가 주문 넣기
        order = client.futures_create_order(
            symbol=symbol.upper(),
            side=side,
            type=ORDER_TYPE_LIMIT,
            quantity=position_size,
            price=price,
            timeInForce=TIME_IN_FORCE_GTC
        )
        order_id = order['orderId']
        print(f"지정가 주문 제출됨: {order_id} @ {price}")

        # 주문 체결 확인: 5분 동안 대기
        start_time = time.time()
        while time.time() - start_time < timeout:
            order_info = client.futures_get_order(symbol=symbol.upper(), orderId=order_id)
            if order_info['status'] == 'FILLED':
                print("✅ 지정가 주문 체결 완료!")
                return 2
            time.sleep(5)

        # 5분 내 체결 안 됨 → 주문 취소
        client.futures_cancel_order(symbol=symbol.upper(), orderId=order_id)
        print("⏰ 시간 초과: 지정가 주문 취소 후 시장가 진입!")

        # 시장가 주문으로 전환
        client.futures_create_order(
            symbol=symbol.upper(),
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=position_size,
            timestamp=safe_timestamp()
        )
        print("🚀 시장가 주문 완료!")
        return 3


    except Exception as e:
        print("오류 발생:", e)
        return 1
    

def reverse_position(symbol):
    # 현재 포지션 정보 가져오기
    positions = client.futures_position_information()
    for position in positions:
        if position["symbol"] == symbol.upper():
            position_size = float(position["positionAmt"])  # 현재 포지션 크기
            if position_size == 0:
                print("현재 포지션 없음. Reverse 불가.")
                return
            
            # 현재 포지션의 방향 (양수: 롱, 음수: 숏)
            if position_size > 0:
                reverse_side = SIDE_SELL  # 롱이면 숏으로 전환
            else:
                reverse_side = SIDE_BUY  # 숏이면 롱으로 전환

            reverse_size = abs(position_size)  # 반대 포지션으로 전환할 크기
            print(f"Reverse Order: {reverse_side} {reverse_size} {symbol}")
            
            # 지정가 주문으로 반대 포지션 실행
            success = place_market_order(symbol, reverse_size, reverse_side)
            print("Reverse 주문 완료")
            return success



def get_position_pnl(symbol):
    """현재 심볼의 포지션 수익률 계산"""
    positions = client.futures_position_information()
    for position in positions:
        if position["symbol"] == symbol.upper():
            position_size = float(position["positionAmt"])
            if position_size == 0:
                return 0, 0  # 포지션 없음
            
            entry_price = float(position["entryPrice"])  # 진입 가격
            unrealized_pnl = float(position["unRealizedProfit"])  # 실현되지 않은 손익

            # 수익률 계산
            pnl_percentage = (unrealized_pnl / (abs(position_size) * entry_price))
            return pnl_percentage, unrealized_pnl
    return 0, 0  # 기본값

def fetch_historical_klines(symbol):
    url = f"https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": max_period,
    }
    response = requests.get(url, params=params)
    key_symbol = symbol.upper()
    if response.status_code == 200:
        data = response.json()

        coin_data[key_symbol]["open"].clear()
        coin_data[key_symbol]["high"].clear()
        coin_data[key_symbol]["low"].clear()
        coin_data[key_symbol]["close"].clear()
        coin_data[key_symbol]["volume"].clear()

        for kline in data:

            coin_data[key_symbol]["open"].append(float(kline[1]))
            coin_data[key_symbol]["high"].append(float(kline[2]))
            coin_data[key_symbol]["low"].append(float(kline[3]))
            coin_data[key_symbol]["close"].append(float(kline[4]))
            coin_data[key_symbol]["volume"].append(float(kline[5]))

        #print("초기 데이터 로드 완료:")

    else:
        print("Error fetching historical data:", response.text)

def get_usdt_balance():
    """현재 선물 계정의 USDT 잔고 가져오기"""
    try:
        balance_info = client.futures_account_balance()
        for asset in balance_info:
            if asset["asset"] == "USDT":
                return float(asset["balance"])  # 총 잔고
    except Exception as e:
        print(f"USDT 잔고 조회 실패: {e}")
    return 0  # 기본값


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    response = requests.post(url, data=data)
    print(response.json())  # 응답 확인

def send_entry_message(symbol, entry_price, position_value, leverage, position):
    message = (
         " strategy 2 (momentum)\n"
        f"🚀 *{position} 진입 완료* 🚀\n"
        f"- 코인: {symbol}\n"
        f"- 가격: {entry_price:,.2f} USDT\n"
        f"- 포지션 밸류: {position_value:.4f} {symbol.replace('USDT', '')}\n"
        f"- 레버리지: {leverage}x"
    )
    send_telegram_message(message)

def send_exit_message(symbol, entry_price, exit_price, position_value, leverage, pnl, pnl_percent, position):
    message = (
         " strategy 2 (momentum)\n"
        f"✅ *{position} 청산 완료* ✅\n"
        f"- 코인: {symbol}\n"
        f"- 진입 가격: {entry_price:,.2f} USDT\n"
        f"- 청산 가격: {exit_price:,.2f} USDT\n"
        f"- 포지션 밸류: {position_value:.4f} {symbol.replace('USDT', '')}\n"
        f"- 레버리지: {leverage}x\n"
        f"- PnL: {pnl:+,.2f} USDT ({pnl_percent:+.2f}%)"
    )
    send_telegram_message(message)

def check_telegram_stop():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    response = requests.get(url)
    messages = response.json().get("result", [])

    for message in messages:
        if "message" in message and "text" in message["message"]:
            text = message["message"]["text"]
            if text.strip() == "정지":
                send_telegram_message("🚨 프로그램을 종료합니다.")
                sys.exit("사용자 요청으로 프로그램 종료됨")

def get_current_position(symbol):
    positions = client.futures_account()['positions']
    for position in positions:
        if position['symbol'] == symbol.upper():
            position_amt = float(position['positionAmt'])
            if position_amt > 0:
                return 'long'
            elif position_amt < 0:
                return 'short'
            else:
                return None
    return None # 심볼을 못 찾았을 경우




# In[4]:


# WebSocket 메시지 처리

'''
def momentum_strategy(symbol):
    
    closes = coin_data[symbol]["close"]
    opens = coin_data[symbol]["open"]
    momentum = coin_data[symbol]["momentum"]

    # 3개 연속 양봉 또는 3개 연속 음봉인지 확인
    is_bullish = (momentum[-2] < 0) & (momentum[-1] >= 0) & (closes[-1] > closes[-2])
    is_bearish = (momentum[-2] < 0) & (momentum[-1] >= 0) & (closes[-1] < closes[-2])  # 음봉 3개 연속


    if not (is_bullish or is_bearish):
        print('해당사항없음')
        return 

    
    symbol = symbol.lower()
    key_symbol = symbol.upper()
    if is_bullish:
        print(key_symbol, coin_data[key_symbol]['position_value'])
        if current_position[key_symbol] == 'long':
            pass
        elif current_position[key_symbol] == 'short':

            pnl_percentage, unrealized_pnl = get_position_pnl(symbol)

            reverse_position(symbol)
            market_price = get_market_price(symbol)
            send_exit_message(symbol, entry_price, market_price, coin_data[key_symbol]['position_value'], leverage, unrealized_pnl, pnl_percentage, 'short')

            position_size = calculate_position_size(coin_data[key_symbol]['position_value'], market_price)
            place_market_order(symbol, position_size, SIDE_BUY)
            send_entry_message(symbol, entry_price, coin_data[key_symbol]['position_value'], leverage, 'long')
            current_position[key_symbol] = 'short'
        elif current_position[key_symbol] == None:
            market_price = get_market_price(symbol)
            entry_price = market_price
            position_size = calculate_position_size(coin_data[key_symbol]['position_value'], market_price)

            place_market_order(symbol, position_size, SIDE_BUY)
            send_entry_message(symbol, entry_price,coin_data[key_symbol]['position_value'], leverage, 'long')
            current_position[key_symbol] = 'long'

    elif is_bearish:
        print(key_symbol, coin_data[key_symbol]['position_value'])
        if current_position[key_symbol] == 'short':
            pass
        elif current_position[key_symbol] == 'long':

            pnl_percentage, unrealized_pnl = get_position_pnl(symbol)
            market_price = get_market_price(symbol)
            reverse_position(symbol)
            send_exit_message(symbol, entry_price, market_price, coin_data[key_symbol]['position_value'], leverage, unrealized_pnl, pnl_percentage, 'long')
            
            position_size = calculate_position_size(coin_data[key_symbol]['position_value'], market_price)
            place_market_order(symbol, position_size, SIDE_SELL)
            send_entry_message(symbol, entry_price, coin_data[key_symbol]['position_value'], leverage, 'short')

            reverse_position(symbol)
            current_position[key_symbol] = 'short'
        elif current_position[key_symbol] == None:
            market_price = get_market_price(symbol)
            entry_price = market_price
            position_size = calculate_position_size(coin_data[key_symbol]['position_value'], market_price)

            place_market_order(symbol, position_size, SIDE_SELL)
            send_entry_message(symbol, entry_price, coin_data[key_symbol]['position_value'], leverage, 'short')

            current_position[key_symbol] = 'short'
'''
def on_message(ws, message):


    global td
    data = json.loads(message)

    if "k" in data:  # Kline 데이터

        kline = data["k"]
        symbol = data["s"].upper()

        if kline["x"]:  # 캔들이 종료되었는지 확인
            open_price = float(kline["o"])
            high_price = float(kline["h"])
            low_price = float(kline["l"])
            close_price = float(kline["c"])
            
            coin_data[symbol]["open"].append(open_price)
            coin_data[symbol]["high"].append(high_price)
            coin_data[symbol]["low"].append(low_price)
            coin_data[symbol]["close"].append(close_price)
            coin_data[symbol]['return'].append((close_price-coin_data[symbol]["close"][-2])/coin_data[symbol]["close"][-2])
            
            data = coin_data[symbol]['return'][-20:]

            rolling_sum = sum(data)  # 합계
            rolling_squared_sum = sum(x**2 for x in data)  # 제곱합

            momentum = rolling_sum**2 - rolling_squared_sum
            coin_data[symbol]['momentum'].append(momentum)


            std = np.std(coin_data[symbol]['return'][-max_period:])
            btc_std = np.std(coin_data['BTCUSDT']['return'][-max_period:])
            account_balance= get_usdt_balance()
            position_value = account_balance * 0.25 * (1/std)/(1/std + 1/btc_std) * leverage
            coin_data[symbol]['position_value'] = position_value

            closes = coin_data[symbol]["close"]
            opens = coin_data[symbol]["open"]
            momentum = coin_data[symbol]["momentum"]

            # 3개 연속 양봉 또는 3개 연속 음봉인지 확인
            is_bullish = (momentum[-2] < 0) & (momentum[-1] >= 0) & (closes[-1] > closes[-2])
            is_bearish = (momentum[-2] < 0) & (momentum[-1] >= 0) & (closes[-1] < closes[-2])


            if not (is_bullish or is_bearish):
                return 

            
            symbol = symbol.lower()
            key_symbol = symbol.upper()
            current_position = get_current_position(key_symbol)
            print(key_symbol, current_position)
            if is_bullish:
                current_position = get_current_position(key_symbol)
                print(key_symbol, coin_data[key_symbol]['position_value'], 'bullish', current_position)
                if current_position == 'long':
                    pass
                elif current_position == 'short':
                    print(key_symbol, 'reverse 시점')
                    pnl_percentage, unrealized_pnl = get_position_pnl(symbol)
                    market_price = get_market_price(symbol)
                    entry_price[key_symbol] = market_price
                    
                    reverse = reverse_position(symbol)
                    print(reverse)
                    
                    if reverse :
                        print('시장가 주문 체결')
                        send_exit_message(symbol, entry_price[key_symbol], market_price, coin_data[key_symbol]['position_value'], leverage, unrealized_pnl, pnl_percentage, 'short')
                    else:
                        print('시장가 주문 실패')

                    position_size = calculate_position_size(coin_data[key_symbol]['position_value'], market_price, symbol)
                    success = place_limit_order_with_auto_cancel(symbol, position_size, SIDE_BUY)

                    if success == 2:
                        print('지정가 주문 체결')
                        send_entry_message(symbol, entry_price[key_symbol], coin_data[key_symbol]['position_value'], leverage, 'long')

                    elif success == 3:
                        print('시장가 주문 체결')
                        send_entry_message(symbol, entry_price[key_symbol], coin_data[key_symbol]['position_value'], leverage, 'long')


                    else :
                        print(f"{key_symbol}: 매수 주문 실패")

                elif current_position == None:
                    market_price = get_market_price(symbol)
                    entry_price[key_symbol] = market_price
                    position_size = calculate_position_size(coin_data[key_symbol]['position_value'], market_price, symbol)

                    success = place_limit_order_with_auto_cancel(symbol, position_size, SIDE_BUY)

                    if success == 2:
                        print('지정가 주문 체결')
                        send_entry_message(symbol, entry_price[key_symbol], coin_data[key_symbol]['position_value'], leverage, 'long')

                    elif success == 3:
                        print('시장가 주문 체결')
                        send_entry_message(symbol, entry_price[key_symbol], coin_data[key_symbol]['position_value'], leverage, 'long')

                    else :
                        print(f"{key_symbol}: 매수 주문 실패")

            elif is_bearish:
                current_position = get_current_position(key_symbol)
                print(key_symbol, coin_data[key_symbol]['position_value'], 'bearish', current_position)
                if current_position == 'short':
                    pass
                elif current_position == 'long':
                    print(key_symbol, 'reverse 시점')
                    pnl_percentage, unrealized_pnl = get_position_pnl(symbol)
                    market_price = get_market_price(symbol)
                    entry_price[key_symbol] = market_price
                    reverse = reverse_position(symbol)
                    
                    if reverse:
                        print('시장가 주문 체결')
                        send_exit_message(symbol, entry_price[key_symbol], market_price, coin_data[key_symbol]['position_value'], leverage, unrealized_pnl, pnl_percentage, 'long')
                    else :
                        print('시장가 주문 실패')

                    position_size = calculate_position_size(coin_data[key_symbol]['position_value'], market_price, symbol)
                    success = place_limit_order_with_auto_cancel(symbol, position_size, SIDE_SELL)

                    if success == 2:
                        print('지정가 주문 체결')
                        send_entry_message(symbol, entry_price[key_symbol], coin_data[key_symbol]['position_value'], leverage, 'short')

                    elif success == 3:
                        print('시장가 주문 체결')


                    else :
                        print(f"{key_symbol}: 매도 주문 실패")  

                elif current_position == None:
                    market_price = get_market_price(symbol)
                    entry_price[key_symbol] = market_price
                    position_size = calculate_position_size(coin_data[key_symbol]['position_value'], market_price, symbol)

                    success = place_limit_order_with_auto_cancel(symbol, position_size, SIDE_SELL)
                    if success == 2:
                        print('지정가 주문 체결')
                        send_entry_message(symbol, entry_price[key_symbol], coin_data[key_symbol]['position_value'], leverage, 'short')

                    elif success == 3:
                        print('시장가 주문 체결')
                        send_entry_message(symbol, entry_price[key_symbol], coin_data[key_symbol]['position_value'], leverage, 'short')

                    else :
                        print(f"{key_symbol}: 매수 주문 실패")

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"WebSocket closed: {close_status_code} - {close_msg}")
    print("Reconnecting in 5 seconds...")
    time.sleep(5)
    start_websocket()  # 웹소켓 다시 실행

def on_open(ws):

    global td
    print("WebSocket 연결 성공!")
    payload = {
        "method": "SUBSCRIBE",
        "params": [f"{symbol}@kline_{interval}" for symbol in symbols],
        "id": 1
    }
    ws.send(json.dumps(payload))

def start_websocket():
    url = "wss://fstream.binance.com/ws"
    ws = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.on_open = on_open
    ws.run_forever()


# In[ ]:


# 초기화
for symbol in symbols :
    key_symbol = symbol.upper()

    fetch_historical_klines(symbol)
    set_leverage(symbol, leverage)
    return_list = []
    momentum_list = []
    entry_price[key_symbol] = None

    for n, close in enumerate(coin_data[key_symbol]['close']):
        if n >= 1:
            return_list.append((coin_data[key_symbol]['close'][n] - coin_data[key_symbol]['close'][n-1])/coin_data[key_symbol]['close'][n-1])
        if n >= 20:
            data = return_list[-20:]

            rolling_sum = sum(data)  # 합계
            rolling_squared_sum = sum(x**2 for x in data)  # 제곱합

            momentum = rolling_sum**2 - rolling_squared_sum
            momentum_list.append(momentum)


    coin_data[key_symbol]['return'] = return_list
    coin_data[key_symbol]['momentum'] = momentum_list
    coin_data[key_symbol]['position_value'] = None

start_websocket()


# In[ ]:





# In[ ]:




