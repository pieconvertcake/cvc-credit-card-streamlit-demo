import os
import pandas as pd
from openai import OpenAI
from fuzzywuzzy import fuzz
import re

class PointMileCalculator:
    def __init__(self, statement_df, point_rate_path, special_points_path, miles_rate_path, openai_api_key):
        os.environ['OPENAI_API_KEY'] = openai_api_key

        # Load DataFrames
        self.statement_spend = statement_df.copy()
        self.cardsdata_pointRate = pd.read_csv(point_rate_path)
        self.cardsdata_specialPoints = pd.read_csv(special_points_path)
        self.cardsdata_milesRate = pd.read_csv(miles_rate_path)

        # Initialize resultPoints DataFrame
        self.resultPoints = self.statement_spend.copy()
        self.initialize_result_points()

    def initialize_result_points(self):
        card_names = pd.unique(self.cardsdata_pointRate["cardName_EN"])
        for card in card_names:
            self.resultPoints[card] = 0
        self.resultPoints.loc['total'] = 0

    def calculate_points(self, spend_amount, interval, points_per_interval):
        return (spend_amount // interval) * points_per_interval

    def calculate_general_points(self):
        for each_spend in self.statement_spend.itertuples():
            spend_amount = each_spend.spendingAmount
            spend_detail = each_spend.spendingDetail
            spend_index = each_spend.Index

            for card in pd.unique(self.cardsdata_pointRate["cardName_EN"]):
                each_card = self.cardsdata_pointRate[self.cardsdata_pointRate["cardName_EN"] == card].iloc[0]
                exception = each_card.exceptFor
                list_of_exception = exception.splitlines()
                interval = each_card.everyBahtSpending
                points_per_interval = each_card.willGetThesePoints

                if not any(fuzz.partial_ratio(spend_detail, ex) > 80 for ex in list_of_exception):
                    points = self.calculate_points(spend_amount, interval, points_per_interval)
                else:
                    points = 0

                self.resultPoints.at[spend_index, card] = points

    def calculate_conditional_points(self):
        condition_check_for_each_spend = self.statement_spend.copy()

        for each_card_row in self.cardsdata_specialPoints.itertuples():
            if each_card_row.spendingType == "แยกรายการ":
                condition = each_card_row.condition
                text_to_llm = f"ตรวจสอบว่าสอดคล้องกับเงื่อนไขนี้หรือไม่ : '{condition}' "

                for i in range(len(self.statement_spend)):
                    text_to_llm += f"\n{i+1}) ใช้จ่าย {self.statement_spend.loc[i, 'spendingDetail']} {self.statement_spend.loc[i, 'spendingAmount']} {self.statement_spend.loc[i, 'currency']}'"

                prompt = text_to_llm
                client = OpenAI()
                completion = client.chat.completions.create(
                    model="gpt-4o-mini-2024-07-18",
                    messages=[
                        {"role": "system", "content": """
                        You are a financial assistant who knows Thai very well.
                        There are multiple questions, and you need to answer all of them.
                        You are allowed to answer only 'true' or 'false' for each question.
                        You should know that 
                          - The user is in Thailand, which means THB is not a foreign currency.
                          - Grab is a online food delivery service, not a restaurant.
                        """},
                        {"role": "user", "content": prompt}
                    ]
                )

                matching_result = completion.choices[0].message.content
                extracted_matching_result = re.findall(r'\d\)\s*(\w+)', matching_result)

                condition_check_for_each_spend[f"{each_card_row.cardName_EN} : {condition}"] = extracted_matching_result

        for each_spend in self.statement_spend.itertuples():
            spend_amount = each_spend.spendingAmount
            spend_detail = each_spend.spendingDetail
            spend_index = each_spend.Index

            for card in condition_check_for_each_spend.columns[5:]:
                cardName_EN, condition = card.split(" : ")
                match_or_not = condition_check_for_each_spend.at[spend_index, card].lower() == "true"

                card_row = self.cardsdata_specialPoints[self.cardsdata_specialPoints["cardName_EN"] == cardName_EN].iloc[0]
                interval = card_row.everyBahtSpending
                points_per_interval = card_row.willGetThesePointsAsAddition

                if match_or_not:
                    points = self.calculate_points(spend_amount, interval, points_per_interval)
                    self.resultPoints.at[each_spend.Index, cardName_EN] += points

    def calculate_cumulative_points(self):
        condition_check_for_each_spend = self.statement_spend.copy()

        for each_card_row in self.cardsdata_specialPoints.itertuples():
            if each_card_row.spendingType == "ยอดสะสม":
                condition = each_card_row.condition
                text_to_llm = f"ตรวจสอบว่าสอดคล้องกับเงื่อนไขนี้หรือไม่ : '{condition}' "

                for i in range(len(self.statement_spend)):
                    text_to_llm += f"\n{i+1}) ใช้จ่าย {self.statement_spend.loc[i, 'spendingDetail']} {self.statement_spend.loc[i, 'spendingAmount']} {self.statement_spend.loc[i, 'currency']}'"

                prompt = text_to_llm
                client = OpenAI()
                completion = client.chat.completions.create(
                    model="gpt-4o-mini-2024-07-18",
                    messages=[
                        {"role": "system", "content": """
                        You are a financial assistant who knows Thai very well.
                        There are multiple questions, and you need to answer all of them.
                        You are allowed to answer only 'true' or 'false' for each question.
                        You should know that 
                          - The user is in Thailand, which means THB is not a foreign currency.
                          - Grab is a online food delivery service, not a restaurant.
                        """},
                        {"role": "user", "content": prompt}
                    ]
                )

                matching_result = completion.choices[0].message.content
                extracted_matching_result = re.findall(r'\d\)\s*(\w+)', matching_result)

                total_sum = 0

                for i in range(len(self.statement_spend)):
                    if extracted_matching_result[i] == "true":
                        total_sum += self.statement_spend.loc[i, 'spendingAmount']
                        if total_sum >= each_card_row.everyBahtSpending:
                            total_sum -= each_card_row.everyBahtSpending
                            self.resultPoints.at[i, each_card_row.cardName_EN] += each_card_row.willGetThesePointsAsAddition

    def sum_calculated_points(self):
        for card in pd.unique(self.cardsdata_pointRate["cardName_EN"]):
            self.resultPoints.at['total', card] = self.resultPoints[card].sum()
    
    def calculate_miles(self):
        resultMiles = self.cardsdata_milesRate.copy()
        resultMiles["calculatedPoints"] = 0
        resultMiles["calculatedMiles"] = 0

        for index, row in resultMiles.iterrows():
            card = row["cardName_EN"]
            airline = row["airlineService"]
            
            if card in self.resultPoints.columns:
                earned_points = self.resultPoints[card].iloc[-1] if not self.resultPoints.empty else 0
            else:
                earned_points = 0

            resultMiles.at[index, "calculatedPoints"] = earned_points

            card_airline_row = self.cardsdata_milesRate[(self.cardsdata_milesRate["cardName_EN"] == card) & (self.cardsdata_milesRate["airlineService"] == airline)]

            if not card_airline_row.empty:
                interval = card_airline_row["everyPointsUsing"].values[0]
                miles_per_interval = card_airline_row["willGetTheseMiles"].values[0]
                earned_miles = earned_points // interval * miles_per_interval
                resultMiles.at[index, "calculatedMiles"] = earned_miles

        return resultMiles

    def export_results(self, output_path):
        self.resultPoints.to_csv(output_path)