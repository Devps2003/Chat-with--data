Sure, here is the updated README with the additional steps to set up `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the environment variables:

---

# Chat-with-Data

Welcome to **Chat-with-Data**! This project integrates a chatbot with Gmail and a MySQL database, allowing you to interact with your data seamlessly using natural language queries.

## Features

- **Gmail Integration:** Fetch emails based on structured queries.
- **Database Interaction:** Query your MySQL database using natural language.
- **Streamlit UI:** An interactive user interface built with Streamlit.
- **OpenAI Integration:** Use OpenAI's GPT model to understand and respond to your queries.

## Getting Started
### Design

![image](https://github.com/Devps2003/Chat-with--data/assets/108901991/ca8156c0-99e6-48bc-90d7-285956f3bd2e)

### Prerequisites

- Python 3.x
- Google Cloud Platform Account
- OpenAI API Key
- MySQL Database

### Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/Devps2003/Chat-with--data.git
   cd Chat-with--data
   ```

2. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Setup Gmail API**

   - Go to the [Google Cloud Console](https://console.cloud.google.com/).
   - Navigate to the API Library and enable the Gmail API.
   - Set up OAuth 2.0 credentials and download the `credentials.json` file.
   - Place the `credentials.json` file in the root directory of the project.
   - On the Google Cloud Console, add the Gmail accounts you want to access.

4. **Set Up Environment Variables**

   - Create a `.env` file in the root directory and add your OpenAI API key:

     ```env
     OPENAI_API_KEY="your_api_key"
     ```

   - Add your Google OAuth 2.0 credentials:

     ```env
     GOOGLE_CLIENT_ID="your_google_client_id"
     GOOGLE_CLIENT_SECRET="your_google_client_secret"
     ```

5. **Prepare MySQL Database**

   - Ensure your MySQL database credentials are ready and accessible.

### Running the Application

1. **Start the Streamlit App**

   ```bash
   streamlit run main.py
   ```

2. **Connect to Database and Gmail**

   - Follow the prompts in the Streamlit app to connect to your MySQL database and Gmail account.

3. **Chat with Your Data**

   - Use the chat interface to ask questions and interact with your data.

### Effortless Database Interaction

**Chat-with-Data** makes it incredibly easy to connect to your MySQL database and retrieve information using natural language queries. No need to write complex SQL queries—simply ask your questions in plain English, and the system will handle the rest. Whether you need to find specific records, run analytical queries, or fetch summary data, **Chat-with-Data** simplifies the process:

- **Example Queries:**
  - "Show me the latest orders."
  - "What are my upcoming meetings?"
  - "Fetch the sales report for last month."

By leveraging the power of OpenAI's GPT model, **Chat-with-Data** interprets your queries, translates them into the necessary SQL commands, and fetches the data for you. This approach dramatically reduces the time and effort required to get the information you need, making data retrieval faster and more intuitive.

## Project Structure

- `main.py`: The main entry point for the Streamlit app.
- `credentials.json`: OAuth 2.0 credentials for Gmail API (to be added).
- `.env`: Environment variables including OpenAI API key, Google Client ID, and Google Client Secret (to be added).
- `requirements.txt`: List of dependencies for the project.

## License

This project is licensed under the MIT License.

## Contributing

Contributions are welcome! Please fork the repository and create a pull request.

## Acknowledgements

- [OpenAI](https://www.openai.com/)
- [Google Cloud](https://cloud.google.com/)
- [Streamlit](https://streamlit.io/)

Feel free to reach out with any questions or suggestions. Enjoy interacting with your data!

---

Make sure to follow these steps carefully to set up and run the application. If you encounter any issues, please refer to the documentation or open an issue on GitHub.

Happy coding! 🚀