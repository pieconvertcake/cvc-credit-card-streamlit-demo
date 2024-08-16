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
point_rate_path = "sample_data/sampleCreditCardsData - pointsRate.csv"
special_points_path = "sample_data/sampleCreditCardsData - specialPoints.csv"
miles_rate_path = "sample_data/sampleCreditCardsData - milesRate.csv"
output_path_calculated_points = "temporary/pointEarned.csv"
output_path_calculated_miles = "temporary/milesEarned.csv"

def fix_statement_final_table(statement_final_table):
    # Check "date" column
    if statement_final_table["date"].dtype == 'O':  # Assuming object type for text
        statement_final_table["date"] = statement_final_table["date"].apply(lambda x: correct(normalize(x)) if is_thai(x) else x)

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
        # Convert the cleaned amount to a float first to handle any remaining decimal places
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

            # Read the PDF into a list of DataFrames using Tabula
            try:
                statement_read_with_tabula = tabula.read_pdf(uploaded_file, pages="all", multiple_tables=True)
            except Exception as e:
                st.error(f"Error reading PDF: {e}")
                return

            # Initialize session state if not already done
            if 'statement_final_cleaned_table' not in st.session_state:
                st.session_state['statement_final_cleaned_table'] = pd.DataFrame()

            # Dictionary to store the selected DataFrames
            selected_dataframes = {}

            # Display options for each DataFrame
            for i, table_df in enumerate(statement_read_with_tabula):
                if not table_df.empty:
                    with st.expander(f"Page {i + 1} - Select columns and include"):
                        st.write(table_df)
                        include_page = st.checkbox(f"Include page {i + 1}", value=True, key=f"include_page_{i}")

                        if include_page:
                            # Generate dropdowns for selecting columns
                            date_col = st.selectbox(f"Select date column for page {i + 1}", table_df.columns, key=f"date_col_{i}")
                            detail_col = st.selectbox(f"Select spendingDetail column for page {i + 1}", table_df.columns, key=f"detail_col_{i}")
                            amount_col = st.selectbox(f"Select spendingAmount column for page {i + 1}", table_df.columns, key=f"amount_col_{i}")
                            currency_col = st.selectbox(f"Select currency column for page {i + 1}", table_df.columns, key=f"currency_col_{i}")

                            # Extract selected columns and store them
                            selected_data = table_df[[date_col, detail_col, amount_col, currency_col]]
                            selected_data.columns = ["date", "spendingDetail", "spendingAmount", "currency"]
                            selected_dataframes[f"page_{i}"] = selected_data

            # Add a button to finalize data processing
            if st.button("Finalize and Display DataFrame"):
                # Combine the selected DataFrames
                if selected_dataframes:
                    combined_df = pd.concat(selected_dataframes.values(), ignore_index=True)
                    # Apply fixes to the combined DataFrame
                    combined_df = fix_statement_final_table(combined_df)
                    st.session_state['statement_final_cleaned_table'] = combined_df.copy()
                    st.write("Combined DataFrame:")
                    st.write(combined_df)
                    combined_df.to_csv("temporary/cleaned_statement.csv")
                else:
                    st.write("No pages selected for inclusion.")

            st.title("Point and Mile Calculator")
            if st.button("Calculate Points and Miles"):

                # Instantiate the calculator
                openai_api_key = os.getenv("OPENAI_API_KEY")
                if not openai_api_key:
                    st.error("API key not found. Please set the OPENAI_API_KEY environment variable.")
                    return
                    
                calculator = PointMileCalculator(st.session_state['statement_final_cleaned_table'], point_rate_path, special_points_path, miles_rate_path, openai_api_key)

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
