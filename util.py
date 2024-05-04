import asyncio
import json
from pathlib import Path
import numpy as np
import pandas as pd
from log import log as logger
from concurrent.futures import ProcessPoolExecutor, wait


class DataCollect(object):

    def __init__(self, save_dir):
        self.save_dir = save_dir
        self.csv_files: list[Path] = self.get_all_csv()

    def get_all_csv(self):
        return [sub_file for sub_file in Path(self.save_dir).iterdir() if
                sub_file.is_file() and sub_file.suffix == ".csv"]

    @staticmethod
    async def csv2json(file_path):
        df = await asyncio.to_thread(pd.read_csv, file_path)
        return json.loads(df.to_json(orient='records', double_precision=4))

    async def get_all_data(self, is_format=True):
        result = await asyncio.gather(*[self.csv2json(file.resolve()) for file in self.csv_files])
        all_data = [{"name": file.stem, "value": result[index]} for index, file in enumerate(self.csv_files)]
        if is_format:
            return self.format_all_data_value(all_data)

    @staticmethod
    def format_all_data_value(all_data: list[dict]):
        start_time = min([data.get("value")[0].get("time") for data in all_data if data.get("value")])
        end_time = max([data.get("value")[-1].get("time") for data in all_data if data.get("value")])

        # 内存操作是cpu密集型但是瓶颈并不在这里使用多进程效果并不明显
        for data in all_data:
            format_all_data_dict = {cur_time: {"time": cur_time} for cur_time in range(start_time, end_time + 1)}
            if data.get("value"):
                old_value = data.get("value")
                for value in old_value:
                    format_all_data_dict[value.get("time")] = value
            data["value"] = list(format_all_data_dict.values())
        return all_data
        # def process_data(data, start_time, end_time):
        #     try:
        #         format_all_data_dict = {cur_time: {"time": cur_time} for cur_time in range(start_time, end_time + 1)}
        #         if data.get("value"):
        #             old_value = data.get("value")
        #             for value in old_value:
        #                 format_all_data_dict[value.get("time")] = value
        #         data["value"] = list(format_all_data_dict.values())
        #         return data
        #     except Exception as e:
        #         logger.error(e)
        #
        # # 假设 all_data 是你的数据列表，start_time 和 end_time 是你的开始和结束时间
        # with ProcessPoolExecutor() as executor:
        #     futures = [executor.submit(process_data, data, start_time, end_time) for data in all_data]
        #     done, not_done = wait(futures)
        #     return done

    # numpy 增强版性能表现更好
    @staticmethod
    def format_all_data_value(all_data):
        start_time = min([data.get("value")[0].get("time") for data in all_data if data.get("value")])
        end_time = max([data.get("value")[-1].get("time") for data in all_data if data.get("value")])
        # 生成时间序列
        all_times = np.arange(start_time, end_time + 1)
        # 遍历所有数据
        for data in all_data:
            if 'value' in data:
                # 将原始数据的时间转换为数组
                original_times = np.array([item['time'] for item in data['value']])
                # 找出缺失的时间点
                missing_times = np.setdiff1d(all_times, original_times)
                # 为缺失的时间点创建新的对象
                missing_data = [{'time': int(time)} for time in missing_times]
                # 将新创建的对象添加到原始数据中
                data['value'].extend(missing_data)
                # 确保数据按照时间排序
                data['value'].sort(key=lambda x: x['time'])
        return all_data
