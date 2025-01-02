import pymysql
import pandas as pd
import os
import zipfile
import requests

def create_daily_timestamp_list(start_date, end_date):
    # 시작 날짜와 끝 날짜 사이의 일별 타임스탬프 리스트 생성
    date_list = []
    daily_list = pd.date_range(start=start_date, end=end_date, freq='D')
    for date in daily_list:
        date_list.append(str(date)[:10])
    return date_list

def download_zip_files(ticker, unit, start_date, end_date):

    base_url = "https://data.binance.vision/data/futures/um/daily/klines/" + ticker + '/' + unit + '/'
    download_dir = "C:\\Users\\Administrator\\Desktop\\업무\\crypto\\data\\" + ticker + unit + 'F'

    dates = pd.date_range(start_date, end_date, freq="D").strftime("%Y-%m-%d").tolist()
    zip_urls = [f"{base_url}{ticker}-{unit}-{date}.zip" for date in dates]

    for url in zip_urls:
        file_name = os.path.join(download_dir, url.split('/')[-1])
        if not os.path.exists(file_name):  # 중복 다운로드 방지
            print(f"Downloading {file_name}...")
            try:
                with requests.get(url, stream=True, verify=False) as r:  # SSL 검사 비활성화
                    r.raise_for_status()
                    with open(file_name, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
            except requests.exceptions.SSLError as e:
                print(f"SSL Error for {url}: {e}")

def extract_and_load_data(ticker, unit, start_date, end_date):

    download_dir = "C:\\Users\\Administrator\\Desktop\\업무\\crypto\\data\\" + ticker + unit + 'F'
    all_data = []
    date_list = create_daily_timestamp_list(start_date, end_date)

    for file_name in os.listdir(download_dir):
        if (file_name.endswith(".zip")) & (file_name[-14:-4] in date_list):
            with zipfile.ZipFile(os.path.join(download_dir, file_name), 'r') as zip_ref:
                zip_ref.extractall(download_dir)
                for csv_file in zip_ref.namelist():
                    if csv_file.endswith(".csv"):
                        file_path = os.path.join(download_dir, csv_file)
                        df = pd.read_csv(file_path, header=None)
                        all_data.append(df)

    # 모든 데이터를 하나의 DataFrame으로 병합
    combined_df = pd.concat(all_data, ignore_index=True)
    return combined_df

ticker = "BTCUSDT"
unit = "1m"
start_date = "2019-12-31"
end_date = "2024-12-31"

#download_zip_files(ticker, unit, start_date, end_date)
combined_data = extract_and_load_data(ticker, unit, start_date, end_date)

columns = ["Open time", "Open", "High", "Low", "Close", "Volume", "Close time", "Quote asset volume", "Number of trades", "Taker buy base asset volume", "Taker buy quote asset volume"]
combined_data = combined_data.iloc[:,:-1]
combined_data.columns = columns
combined_data = combined_data[combined_data['Open time'] != 'open_time']
print(combined_data)

# MySQL 서버에 연결
connection = pymysql.connect(
    host="127.0.0.1",  # MySQL 서버의 주소
    user="root",        # MySQL 사용자 이름
    port=3306,
    database='crypto',
    password="cdfha!3579",  # 비밀번호
    charset='utf8'
)
cur = connection.cursor()

table_name = ticker + unit +'F'
create_table_query = f"""
CREATE TABLE IF NOT EXISTS {table_name} (
    `Open time` BIGINT,
    `Open` FLOAT,
    `High` FLOAT,
    `Low` FLOAT,
    `Close` FLOAT,
    `Volume` FLOAT,
    `Close time` BIGINT,
    `Quote asset volume` FLOAT,
    `Number of trades` INT,
    `Taker buy base asset volume` FLOAT,
    `Taker buy quote asset volume` FLOAT
)
"""
cur.execute(create_table_query)
for _, row in combined_data.iterrows():
    insert_query = f"""
    INSERT INTO {table_name} (
        `Open time`, `Open`, `High`, `Low`, `Close`, `Volume`, 
        `Close time`, `Quote asset volume`, `Number of trades`, 
        `Taker buy base asset volume`, `Taker buy quote asset volume`
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    cur.execute(insert_query, (
        row["Open time"], row["Open"], row["High"], row["Low"], row["Close"], row["Volume"],
        row["Close time"], row["Quote asset volume"], row["Number of trades"],
        row["Taker buy base asset volume"], row["Taker buy quote asset volume"]
    ))

# 변경사항 커밋 및 연결 종료
connection.commit()
print("데이터가 성공적으로 MySQL 테이블에 저장되었습니다.")
connection.close()