import os
import time
import requests
import pandas as pd
import streamlit as st
from azure.storage.blob import BlobServiceClient, ContentSettings
import io

import json

def upload_pdf_to_azure(uploaded_file):
    """
    Uploads a PDF file to an Azure Blob Storage container.
    This function initializes a connection to Azure Blob Storage using the connection string
    and container name from Streamlit secrets. It ensures the container exists, creates it if not,
    and uploads the provided PDF file to the container. The function returns the URL of the uploaded
    file or None if an error occurs.
    Args:
        uploaded_file (UploadedFile): The PDF file to be uploaded.
    Returns:
        str: The URL of the uploaded file if successful, None otherwise.
    Raises:
        Exception: If an error occurs during the upload process, an error message is displayed
                   using Streamlit's error function.
    """
    try:
        # Initialize the BlobServiceClient with the connection string
        blob_service_client = BlobServiceClient.from_connection_string(
            st.secrets["AZURE_STORAGE_CONNECTION_STRING"]
        )

        # Get a client for the container
        container_client = blob_service_client.get_container_client(
            st.secrets["AZURE_CONTAINER_NAME"]
        )

        # Ensure container exists, create if not
        if not container_client.exists():
            container_client.create_container()

        # Extract the filename from the uploaded file
        blob_name = uploaded_file.name

        # Create a blob client for the file
        blob_client = container_client.get_blob_client(blob_name)

        # Upload the file directly from the uploaded_file object
        blob_client.upload_blob(
            uploaded_file,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/pdf"),
        )

        # Construct the URL to the uploaded blob
        blob_url = f"https://{st.secrets['AZURE_STORAGE_ACCOUNT_NAME']}.blob.core.windows.net/{st.secrets['AZURE_CONTAINER_NAME']}/{blob_name}"

        st.success(f"Upload successful. File URL: {blob_url}")        
        return blob_url

    except Exception as e:
        st.error(f"An error occurred during upload: {str(e)}")
        return None


def analyze_pdf(pdf_path_or_url, is_url=False):
    """
    Analyzes a PDF document using the Azure Form Recognizer service.
    Args:
        pdf_path_or_url (str): The file path or URL of the PDF document to be analyzed.
        is_url (bool): A flag indicating whether the input is a URL (True) or a file path (False). Default is False.
    Returns:
        str or None: The extracted content from the PDF if the analysis is successful, otherwise None.
    Raises:
        Exception: If an error occurs during the PDF analysis process.
    Notes:
        - The function uses the Azure Form Recognizer service to analyze the PDF document.
        - The service endpoint and API key are retrieved from Streamlit secrets.
        - If the analysis is initiated successfully, the function polls the operation location until the analysis is complete.
        - If the analysis succeeds, the extracted content is returned. If no content is found, a warning is displayed.
        - If an error occurs during the process, an error message is displayed.
    """

    analyze_url = f"{st.secrets['DOC_INTEL_ENDPOINT']}/formrecognizer/documentModels/prebuilt-read:analyze?api-version=2023-07-31"
    headers = {
        "Content-Type": "application/json" if is_url else "application/octet-stream",
        "Ocp-Apim-Subscription-Key": st.secrets["DOC_INTEL_API_KEY"],
    }

    try:
        if is_url:
            data = {"urlSource": pdf_path_or_url}
            response = requests.post(analyze_url, headers=headers, json=data)
        else:
            response = requests.post(
                analyze_url, headers=headers, data=pdf_path_or_url.read()
            )

        if response.status_code == 202:
            operation_location = response.headers["Operation-Location"]
            while True:
                result_response = requests.get(
                    operation_location,
                    headers={
                        "Ocp-Apim-Subscription-Key": st.secrets["DOC_INTEL_API_KEY"]
                    },
                )
                result_json = result_response.json()

                if result_json["status"] in ["succeeded", "failed"]:
                    break
                time.sleep(1)

            # Check if the analysis succeeded
            if result_json["status"] == "succeeded":
                if (
                    "analyzeResult" in result_json
                    and "content" in result_json["analyzeResult"]
                ):
                    return result_json["analyzeResult"]["content"]
                else:
                    st.warning("No content found in the analysis response.")
                    return None
        else:
            st.error(f"Error in initiating analysis: {response.json()}")
            return None
    except Exception as e:
        st.error(f"An error occurred during PDF analysis: {str(e)}")
        return None


def ask_openai(question, context):
    """
    Sends a question to the OpenAI API with a given context and retrieves the response.
    Args:
        question (str): The question to ask the OpenAI API.
        context (str): The context to provide to the OpenAI API for better understanding of the question.
    Returns:
        str: The response from the OpenAI API if the request is successful.
        None: If there is an error in the request or an exception occurs.
    Raises:
        Exception: If an error occurs during the API request.
    """
    
    
    ### TODO: Implement AI Search to get files from our knowledge base
    ### For now, simply print out the names of the files in the container
    
    # Initialize the BlobServiceClient with the connection string
    blob_service_client = BlobServiceClient.from_connection_string(
        st.secrets["AZURE_STORAGE_CONNECTION_STRING"]
    )
    
    # Get a client for the container
    container_client = blob_service_client.get_container_client(
        st.secrets["AZURE_KNOWLEDGE_BASE_CONTAINER_NAME"]
    )
    
    # List all blobs in the knowledge base container
    knowledge_base_blob_list = container_client.list_blobs()
    
    st.write("### Files in the knowledge base:")
    for blob in knowledge_base_blob_list:
        # write blobs as list items
        st.write(f"- {blob.name}")
    
    
    
    
    
    
    

    headers = {
        "Content-Type": "application/json",
        "api-key": st.secrets["OPENAI_API_KEY"],
    }

    messages = [
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
    ]
    data = {"messages": messages, "max_tokens": 2000, "temperature": 0.7}

    try:
        response = requests.post(
            st.secrets["OPENAI_ENDPOINT"], headers=headers, json=data
        )

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            st.error(f"Error in OpenAI request: {response.json()}")
            return None
    except Exception as e:
        st.error(f"An error occurred during OpenAI query: {str(e)}")
        return None


st.header("AI-Driven Project Estimation Tool")

# Add session state to store results
if "extracted_text" not in st.session_state:
    st.session_state.extracted_text = None

if "ai_response" not in st.session_state:
    st.session_state.ai_response = None

uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file:
    with st.spinner("Uploading and analyzing PDF..."):
        pdf_url = upload_pdf_to_azure(uploaded_file)

        if pdf_url:
            if st.session_state.extracted_text is None:
                st.session_state.extracted_text = analyze_pdf(pdf_url, is_url=True)

            if st.session_state.extracted_text:
                st.success("PDF analysis complete!")

                # Prepare question for OpenAI
                user_question = """
                    Your role is to analyze the project outline document, and for each task to estimate man-days, suggest fitting roles, and outline potential issues.

                    Limit yourself to 10 detailed tasks for now. The tasks should be 1 specific task in the project. For example "Create the login screen for the web-app", and not "Frontend development".

                    Please generate detailed estimations in JSON format as shown below. Follow these guidelines, and don't include comments in the JSON structure:


                    1. **MSCW**: The priority of the task. The options are: "1 Must Have", "2 Should Have", "3 Could Have"
                    2. **Area**: The area of the project where the task belongs. The options are: "01 Analyze & Design", "03 Setup", "04 Development"
                    3. **Module**: The software engineering domain of the task. The options are: "Overall", "Frontend", "Middleware", "Infra", "IoT", "Security"
                    4. **Feature**: What exactly is being done in the task. The options are: "General", "Technical Lead", "Project Manager", "Sprint Artifacts & Meetings", "Technical Analysis", "Functional Analysis", "User Experience (UX)", "User Interface (UI)", "Security Review", "Go-Live support", "Setup Environment + Azure", "Setup Projects", "Authentication & Authorizations", "Monitoring", "Notifications", "Settings" , "Filtering / search"
                    5. **Task**: Summarize the task in a detailed sentence or two.
                    6. **Profile**: The role of the person who will perform the task. The options are: "0 Blended FE dev", "0 Blended MW dev", "0 Blended Overall dev, 0 Blended XR dev", "1 Analyst", "2 Consultant Technical", "3 Senior Consultant Technical", "4 Lead Expert", "5 Manager", "6 Senior Manager", "7 DPH Consultant Technical", "8 DPH Senior Consultant Technical", "9 DPH Lead Expert/Manager"
                    7. **MinDays**: The estimated minimum number of days required to complete the task.
                    8. **RealDays**: The average or most likely number of days required to complete the task.
                    9. **MaxDays**: The estimated maximum number of days required to complete the task.
                    10. **Contingency**: for this write "0" for now.
                    11. **EstimatedDays**: this is a formula that calculates the estimated days based on the MinDays, RealDays, and MaxDays. The formula is: (MinDays + (4 * RealDays) + (4 * MaxDays)) / 9. Make sure to round up to the nearest whole number.
                    12. **EstimatedPrice**: this is a formula that calculates the estimated price based on the EstimatedDays and the cost of the Profile. For now use 200 as the cost per day. The formula is: EstimatedDays * 200.
                    13. **Potential Issues**: List potential risks or issues that might arise, such as “security concerns,” “data compliance requirements,” or “scope changes.”

                    
                    General pointers:
                        - Keep the estimated days low. Anywhere from 0 for MinDays to 4 days for MaxDays is a good estimate.
                        - It is possible for a task to be done within a day, so don't hesitate to use 0 for MinDays, and 0.5 for RealDays.
                        - Make sure not to use the same Area for every task. Try to distribute the tasks across different Areas.
                        - Make sure to use a wide variety of Profiles for the tasks. Don't use the same Profile for every task.
                        - Make sure to have different MSCW priorities for the tasks. Make sure to have at least two tasks for each priority.
                        - Make sure to vary in your usage of Profile. Do not use the same Profile for every task.


                    Return the response in this JSON structure:
                    
                    ```json
                    {
                        "list_of_all_tasks": [
                            {
                                "MSCW": "1 Must Have",
                                "Area": "01 Analyze & Design",
                                "Module": "Overall",
                                "Feature": "General",
                                "Task": "Task 1 description",
                                "Profile": "1 Analyst",
                                "MinDays": 1,
                                "RealDays": 2,
                                "MaxDays": 3,
                                "Contingency": 0,
                                "EstimatedDays": 3,
                                "EstimatedPrice": 600,
                                "potential_issues": [
                                    "Issue 1",
                                    "Issue 2",
                                    "Issue 3"
                                ]
                            },
                            // Additional tasks follow
                        ]    
                    }
                    ```
                """

                if st.session_state.ai_response is None:
                    with st.spinner("Querying OpenAI..."):
                        st.session_state.ai_response = ask_openai(
                            user_question, st.session_state.extracted_text
                        )

                if st.session_state.ai_response:
                    st.success("OpenAI analysis complete!")

                    # Convert JSON to DataFrame and prepare download buttons
                    try:
                        response_data = st.session_state.ai_response
                        df = pd.read_json(
                            io.StringIO(response_data)
                        )  # Parse JSON from the response
                        if "list_of_all_tasks" in df:
                            df = pd.json_normalize(df["list_of_all_tasks"])

                            st.write(df)

                            # Export to Excel
                            excel_buffer = io.BytesIO()
                            with pd.ExcelWriter(
                                excel_buffer, engine="openpyxl"
                            ) as writer:
                                df.to_excel(writer, index=False, sheet_name="Tasks")
                            excel_buffer.seek(0)

                            st.download_button(
                                label="Download Excel",
                                data=excel_buffer,
                                file_name="response.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                            

                            # Export to profiles to JSON
                            profile_data = df["Profile"].to_json(index=False).encode("utf-8")
                            st.download_button(
                                label="Export Profiles to JSON",
                                data=profile_data,
                                file_name="project_profiles.json",
                                mime="text/json",
                            )
                            
                            
                        else:
                            st.error(
                                "Failed to extract tasks: Check the prompt or OpenAI response structure."
                            )
                    except Exception as e:
                        st.error(f"Error while processing OpenAI response: {str(e)}")
