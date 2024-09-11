import os
import pandas as pd
from openai import OpenAI
from io import StringIO

class TransactionsExtractor:
    def __init__(self, text_from_tabula, openai_api_key):
        os.environ['OPENAI_API_KEY'] = openai_api_key
        
        # Load DataFrames
        self.text_from_tabula = text_from_tabula

    def extract_only_tracsaction(self):
        client = OpenAI()
        completion = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": """
                You are a financial assistant capable of understanding Thai.
                You will receive raw text extracted from a PDF bank statement, which may contain some noise or irrelevant information.
                Your task is to clean and extract valid transaction data and return the results in CSV format with the following columns:
                    - "date" (in YYYY-MM-DD format)
                    - "spendingDetail" (a brief description of the transaction)
                    - "spendingAmount" (the amount of money spent)
                    - "currency" (the currency used, such as THB, USD, CNY, JPY)
                Please ensure that only valid transaction rows are included. The output should be comma-separated and ready to be written directly into a CSV file.
                Ensure no additional text or formatting is present, just the valid CSV content.
                """},
            {"role": "user", "content": self.text_from_tabula}
            ]
        )

        result = completion.choices[0].message.content
        cleaned_result = result.strip("```").strip("```")
        if cleaned_result.startswith("csv"):
            cleaned_result = cleaned_result[len("csv"):]
        print("Raw CSV result from OpenAI:", cleaned_result)
                    
        # Convert the result into a DataFrame
        result_df = pd.read_csv(StringIO(cleaned_result))

        return result_df
