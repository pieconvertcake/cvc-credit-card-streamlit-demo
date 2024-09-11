from point_mile_calculator import PointMileCalculator
from statement_extractor import TransactionsExtractor
import streamlit as st
import pandas as pd
import os
from io import StringIO
from google.cloud import documentai_v1beta3 as documentai
from google.oauth2 import service_account
from PIL import Image
import io

# Replace these with your actual file paths and API key
point_rate_path = "sample_data/sampleCreditCardsData - pointsRate.csv"
special_points_path = "sample_data/sampleCreditCardsData - specialPoints.csv"
miles_rate_path = "sample_data/sampleCreditCardsData - milesRate.csv"
output_path_calculated_points = "temporary/pointEarned.csv"
output_path_calculated_miles = "temporary/milesEarned.csv"

# Helper function to get the text from a given layout
def get_text(layout, document):
    """Extracts text based on the layout's text segments."""
    text_segments = []
    for segment in layout.text_anchor.text_segments:
        start_index = segment.start_index
        end_index = segment.end_index
        text_segments.append(document.text[start_index:end_index])
    return ''.join(text_segments)


def my_demo():
    st.title("Upload your bank statement (.pdf, .png, .jpg)")

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        st.error("API key not found. Please set the OPENAI_API_KEY environment variable.")
        return

    # Load the credentials from Streamlit secrets
    service_account_info = {
        "type": st.secrets["connections"]["gcs"]["type"],
        "project_id": st.secrets["connections"]["gcs"]["project_id"],
        "private_key_id": st.secrets["connections"]["gcs"]["private_key_id"],
        "private_key": st.secrets["connections"]["gcs"]["private_key"],
        "client_email": st.secrets["connections"]["gcs"]["client_email"],
        "client_id": st.secrets["connections"]["gcs"]["client_id"],
        "auth_uri": st.secrets["connections"]["gcs"]["auth_uri"],
        "token_uri": st.secrets["connections"]["gcs"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["connections"]["gcs"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["connections"]["gcs"]["client_x509_cert_url"],
    }
    
    # Load credentials from the parsed service account info
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    
    # Set up the Document AI client
    client = documentai.DocumentProcessorServiceClient(credentials=credentials)

    # File uploader widget: accept both PDF and image files
    uploaded_file = st.file_uploader("Choose a file (PDF, PNG, JPG)", type=["pdf", "png", "jpg", "jpeg"])

    # The processor name from Document AI (replace with your processor's name)
    processor_name = "projects/856865964624/locations/us/processors/638605b6f58ceffe"

    if uploaded_file is not None:
        try:

            # Check if the uploaded file is an image or a PDF
            if uploaded_file.type in ["image/png", "image/jpeg", "image/jpg"]:
                # Read the image using PIL
                image = Image.open(uploaded_file)
                
                # Convert the image to bytes (Google Document AI needs bytes format)
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format=image.format)
                file_bytes = img_byte_arr.getvalue()
                
                mime_type = f"image/{image.format.lower()}"
            
            else:
                # Read the uploaded PDF file as bytes
                file_bytes = uploaded_file.read()
                mime_type = "application/pdf"

            # Prepare the raw document request for Document AI
            document = {"content": file_bytes, "mime_type": mime_type}

            # Create a request to process the document
            request = {"name": processor_name, "raw_document": document}

            # Process the document using Document AI
            result = client.process_document(request=request)

            # Get the document from the response
            document = result.document

            # Initialize an empty string to store extracted text
            statement_read_with_documentai_in_text = ""
            extracted_tables = []

            # Extract pages from the processed document
            for page in document.pages:
                # Process the tables
                for table in page.tables:
                    table_data = []

                    # Extract rows and cells
                    for row in table.body_rows:
                        row_data = []
                        for cell in row.cells:
                            # Extract text segment for each cell
                            cell_text = get_text(cell.layout, document)
                            row_data.append(cell_text)
                        table_data.append(row_data)

                    # Convert to DataFrame
                    df = pd.DataFrame(table_data)
                    extracted_tables.append(df)

                    # Convert DataFrame to CSV as text
                    csv_text = StringIO()
                    df.to_csv(csv_text, index=False)

                    # Append the CSV text to the final string
                    each_df_to_txt = csv_text.getvalue()
                    statement_read_with_documentai_in_text += "\na detected table:\n"
                    statement_read_with_documentai_in_text += each_df_to_txt

            print(statement_read_with_documentai_in_text)

            # Combine all extracted DataFrames if necessary
            combined_df = pd.concat(extracted_tables, ignore_index=True)

            # Assuming you have an extractor class that takes the string format
            extractor = TransactionsExtractor(statement_read_with_documentai_in_text, openai_api_key)
            extracted_statement_transactions_df = extractor.extract_only_tracsaction()

            # Save the final cleaned table in session state
            st.session_state['statement_final_cleaned_table'] = extracted_statement_transactions_df.copy()

            st.write("Extracted transactions from your statement:")
            st.write(extracted_statement_transactions_df)

        except Exception as e:
            st.error(f"An error occurred: {e}")


    st.title("Point and Mile Calculator")

    if st.button("Calculate Points and Miles"):
        # Instantiate the calculator
        calculator = PointMileCalculator(st.session_state['statement_final_cleaned_table'], point_rate_path, special_points_path, miles_rate_path, openai_api_key)

        try:
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

        except Exception as e:
            st.error(f"Error calculating points and miles: {e}")

if __name__ == "__main__":
    my_demo()
