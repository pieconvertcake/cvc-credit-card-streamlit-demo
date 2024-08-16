from point_mile_calculator import PointMileCalculator
import streamlit as st
import pandas as pd
import pdfplumber
import tabula
import re
from pythainlp.util import normalize
from pythainlp.spell import correct
import os

# Replace these with your actual file paths and API key
# statement_path = "sample_data/sampleStatement.csv"
# statement_path = "temporary/cleaned_statement.csv"
statement_final_cleaned_table = pd.DataFrame()
point_rate_path = "sample_data/sampleCreditCardsData - pointsRate.csv"
special_points_path = "sample_data/sampleCreditCardsData - specialPoints.csv"
miles_rate_path = "sample_data/sampleCreditCardsData - milesRate.csv"
output_path_calculated_points = "temporary/pointEarned.csv"
output_path_calculated_miles = "temporary/milesEarned.csv"

def fix_statement_final_table(statement_final_table):
    # Check "date" column
    if statement_final_table["date"].dtype == 'O':  # Assuming object type for text
        statement_final_table["date"] = statement_final_table["date"].apply(lambda x: correct(normalize(x)) if is_thai(x) else x)
        # statement_final_table["date"] = pd.to_datetime(statement_final_table["date"], errors='coerce', format='%Y-%m-%d')

    # Check "spendingDetail" column
    statement_final_table["spendingDetail"] = statement_final_table["spendingDetail"].apply(lambda x: correct(normalize(x)) if is_thai(x) else x)

    # Check "spendingAmount" column
    def fix_spending_amount(amount):
        # Remove any non-numeric characters except for commas and periods
        cleaned_amount = re.sub(r'[^\d.,-]', '', amount)
        cleaned_amount = cleaned_amount.replace(',', '')

        # Convert to a positive number
        cleaned_amount = cleaned_amount.lstrip('-')
        cleaned_amount = cleaned_amount.strip()
        # Convert the cleaned amount to a float first to handle any remaining decimal places, then to an integer
        return float(cleaned_amount) if cleaned_amount else None

    statement_final_table["spendingAmount"] = statement_final_table["spendingAmount"].apply(fix_spending_amount)

    # Check "currency" column
    def fix_currency(currency):
        recognized_currencies = ["THB", "USD", "EUR", "JPY", "GBP"]  # Add more as needed
        for cur in recognized_currencies:
            if cur in currency.upper():
                return cur
        return "THB"  # Default to THB if no currency found

    statement_final_table["currency"] = statement_final_table["currency"].apply(fix_currency)

    return statement_final_table

def is_thai(text):
    # Simple check to see if the text contains Thai characters
    return bool(re.search(r'[\u0E00-\u0E7F]', text))


def pdf_manager():
    st.title("Upload your bank statement (.pdf)")

    # File uploader widget
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

    if uploaded_file is not None:
        # Open the PDF with PDFPlumber
        with pdfplumber.open(uploaded_file) as statement_pdf_file:
            # Display the number of pages in the PDF
            num_pages = len(statement_pdf_file.pages)
            st.write(f"Number of pages: {num_pages}")

            # Placeholder DataFrame
            statement_final_table = pd.DataFrame(columns=["date", "spendingDetail", "spendingAmount", "currency"])
            
            # Read the PDF into a list of DataFrames using Tabula
            statement_read_with_tabula = tabula.read_pdf(uploaded_file, pages="all", multiple_tables=True)
            
            for i in range(num_pages):
                st.write(f"Page {i + 1}")
                st.write(statement_read_with_tabula[i])

                if not statement_read_with_tabula[i].empty:
                    # Generate dropdowns for selecting columns
                    date_col = st.selectbox(f"Select date column for page {i + 1}", statement_read_with_tabula[i].columns)
                    detail_col = st.selectbox(f"Select spendingDetail column for page {i + 1}", statement_read_with_tabula[i].columns)
                    amount_col = st.selectbox(f"Select spendingAmount column for page {i + 1}", statement_read_with_tabula[i].columns)
                    currency_col = st.selectbox(f"Select currency column for page {i + 1}", statement_read_with_tabula[i].columns)

                    # Extract selected columns and append to statement_final_table
                    selected_data = statement_read_with_tabula[i][[date_col, detail_col, amount_col, currency_col]]
                    selected_data.columns = ["date", "spendingDetail", "spendingAmount", "currency"]
                    statement_final_table = pd.concat([statement_final_table, selected_data], ignore_index=True)

            # Add a button to finalize data processing
            if st.button("Finalize and Display DataFrame"):
                # Apply fixes to the combined DataFrame
                statement_final_table = fix_statement_final_table(statement_final_table)
                global statement_final_cleaned_table 
                statement_final_cleaned_table = statement_final_table.copy()
                st.write("Combined DataFrame:")
                st.write(statement_final_table)
                statement_final_table.to_csv("temporary/cleaned_statement.csv")
            
            st.title("Point and Mile Calculator")
            if st.button("Calculate Points and Miles"):

                # Instantiate the calculator
                openai_api_key = os.getenv("OPENAI_API_KEY")
                global statement_final_cleaned_table 
                calculator = PointMileCalculator(statement_final_cleaned_table, point_rate_path, special_points_path, miles_rate_path, openai_api_key)

                # Perform calculations
                calculator.calculate_general_points()
                calculator.calculate_conditional_points()
                calculator.calculate_cumulative_points()
                calculator.sum_calculated_points()
                resultMiles = calculator.calculate_miles()

                # Export results to CSV
                calculator.export_results(output_path_calculated_points)

                st.success("Calculations complete and results exported!")
                
                # Recommendation for the best card based on miles
                if 'calculatedMiles' in resultMiles.columns:
                    max_miles_row = resultMiles.loc[resultMiles['calculatedMiles'].idxmax()]
                    max_miles_card = max_miles_row["cardName_EN"]
                    max_miles_airline = max_miles_row["airlineService"]
                    max_miles_value = max_miles_row["calculatedMiles"]
                    st.subheader("Recommended Card for Miles")
                    st.write(f"The card with the maximum miles is `{max_miles_card}` with {max_miles_value} miles for {max_miles_airline}.")
                else:
                    st.write("No calculated miles available for comparison.")

                # Display results
                st.subheader("Points Earned:")
                st.write(calculator.resultPoints)

                st.subheader("Miles Calculated:")
                st.write(resultMiles)

def point_and_mile_calculator():
    st.title("Point and Mile Calculator")

    # Instantiate the calculator
    calculator = PointMileCalculator(statement_path, point_rate_path, special_points_path, miles_rate_path, openai_api_key)

    # Perform calculations
    calculator.calculate_general_points()
    calculator.calculate_conditional_points()
    calculator.calculate_cumulative_points()
    calculator.sum_calculated_points()
    resultMiles = calculator.calculate_miles()

    # Export results to CSV
    calculator.export_results(output_path_calculated_points)

    st.success("Calculations complete and results exported!")
    
    # Recommendation for the best card based on miles
    if 'calculatedMiles' in resultMiles.columns:
        max_miles_row = resultMiles.loc[resultMiles['calculatedMiles'].idxmax()]
        max_miles_card = max_miles_row["cardName_EN"]
        max_miles_airline = max_miles_row["airlineService"]
        max_miles_value = max_miles_row["calculatedMiles"]
        st.subheader("Recommended Card for Miles")
        st.write(f"The card with the maximum miles is `{max_miles_card}` with {max_miles_value} miles for {max_miles_airline}.")
    else:
        st.write("No calculated miles available for comparison.")

    # Display results
    st.subheader("Points Earned:")
    st.write(calculator.resultPoints)

    st.subheader("Miles Calculated:")
    st.write(resultMiles)

if __name__ == "__main__":
    pdf_manager()
