import streamlit as st
import re
import csv
import os
import pandas as pd
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient, models
import folium
from streamlit_folium import folium_static
from geopy.geocoders import Nominatim
import requests
import polyline



from groq import Groq

# Initialize the Groq client with your API key
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# Function to use the Groq API to generate a response
def generate_response( user_query):
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful  First Aid assistant. Give Answer Releated to the health or medical only"},
            {"role": "user", "content": user_query},
        ],
        model="llama3-8b-8192",
        temperature=0.5,
        max_tokens=1024,
        top_p=1,
        stop=None,
        stream=False,
    )

    return chat_completion.choices[0].message.content

# Function to display the chatbot interface
def chat_interface():
    st.title("First Aid Chatbot")

    if "history" not in st.session_state:
        st.session_state.history = []


    # User input section
    with st.form(key='user_input_form'):
        user_input = st.text_input("You:", key="input")
        submit_button = st.form_submit_button(label="Send")

    # Display chat history
    for message in st.session_state.history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # If the user sends a message
    if submit_button and user_input:
        # Add user input to the chat history
        st.session_state.history.append({"role": "user", "content": user_input})
        
        # Generate model response using Groq API
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = generate_response(user_input)
                st.markdown(response)
                st.warning("In the case of emergency contact with doctor.Generated responce may be invalid so validate it first.")

        # Add model response to the chat history
        st.session_state.history.append({"role": "assistant", "content": response})






# Initialize Qdrant client
qdrant_client = QdrantClient(
    url="1c567b57-a9a3-4959-95a8-a20ce9b0f0d5.europe-west3-0.gcp.cloud.qdrant.io:6333",
    api_key="i4WNjeJf7IbnjniOr_r7QpTvGIABQ0tT9G7ngCB7UC03QeeSiHjsrw",
)

# Initialize your embedding model
model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
search_results = {}
adress = ""
# File to store user credentials
USER_CSV = "users.csv"


def get_location_coordinates(location_name):
    geolocator = Nominatim(user_agent="my_streamlit_map_application")
    try:
        location = geolocator.geocode(location_name)
        if location:
            return location.latitude, location.longitude
        else:
            return None
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def get_route(start_lon, start_lat, end_lon, end_lat):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=polyline"
    response = requests.get(url)
    if response.status_code == 200:
        route_data = response.json()
        if route_data["code"] == "Ok":
            return route_data["routes"][0]["geometry"]
    return None

def create_map_with_route(start_lat, start_lon, end_lat, end_lon):
    # Create map centered around the route
    m = folium.Map(location=[(start_lat + end_lat) / 2, (start_lon + end_lon) / 2], zoom_start=10)
    
    # Add markers for start and end
    folium.Marker([start_lat, start_lon], popup="Start", icon=folium.Icon(color='green')).add_to(m)
    folium.Marker([end_lat, end_lon], popup="End", icon=folium.Icon(color='red')).add_to(m)
    
    # Get the route
    route_polyline = get_route(start_lon, start_lat, end_lon, end_lat)
    
    if route_polyline:
        # Decode the polyline
        route_coords = polyline.decode(route_polyline)
        
        # Add the route to the map
        folium.PolyLine(locations=route_coords, color='blue', weight=5, opacity=0.8).add_to(m)
        
        # Fit the map to the route
        southwest = min(route_coords, key=lambda coord: (coord[0], coord[1]))
        northeast = max(route_coords, key=lambda coord: (coord[0], coord[1]))
        m.fit_bounds([southwest, northeast])
    else:
        st.warning("Unable to find a route between the given locations.")
    
    return m

# Function to validate email
def validate_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# Function to validate password
def validate_password(password):
    return len(password) >= 8

# Function to check if email exists in CSV
def email_exists(email):
    if os.path.exists(USER_CSV):
        with open(USER_CSV, mode='r') as file:
            reader = csv.reader(file)
            for row in reader:
                if row[0] == email:
                    return True
    return False

# Function to add a new user to CSV
def add_user_to_csv(email, password):
    with open(USER_CSV, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([email, password])

# Function to validate login credentials from CSV
def validate_login(email, password):
    if os.path.exists(USER_CSV):
        with open(USER_CSV, mode='r') as file:
            reader = csv.reader(file)
            for row in reader:
                if row[0] == email and row[1] == password:
                    return True
    return False

# Create tabs for sign-up and login
def main():
    if st.session_state.get("logged_in", False):
        
     tabs = ["Hospital Information", "First Aid Chatbot"]
     tab = st.tabs(tabs)
     with tab[0]: 
        
        st.title("Welcome to the Hospitrex by Akira")

        # Create two columns
        col1, col2 = st.columns(2)

        # Display the first two inputs in the same row
        with col1:
            country = st.selectbox("Choose a country:", ["Pakistan", "India", "America"])

        with col2:
            hospital_name = st.text_input("Name of the hospital")
            

        # Display the next two inputs below the first row
        city = st.text_input("City in which you are looking for a hospital")
        location = st.text_input("Your Current Location")
        if st.button("Get Location"):
            if country == "Pakistan":
                            # Define the collection name
                collection_name = "Pakistan-Hospitals"

                # Search for hospitals based on city and query text
                def search_hospitals_by_city(city: str, query_text: str, limit=1):
                    # Convert query text to embedding
                    query_embedding = model.encode(query_text).tolist()
                    city = city.capitalize()
                    # Define the filter for the city
                    city_filter = models.Filter(
                        must=[
                            models.FieldCondition(
                                key="CITY",
                                match=models.MatchValue(value=city)
                            )
                        ]
                    )
                    
                    # Search for similar vectors within the filtered city
                    search_results = qdrant_client.search(
                        collection_name=collection_name,
                        query_vector=query_embedding,  # Corrected argument name
                        limit=limit,
                        query_filter=city_filter  # Using 'query_filter' to filter by city
                    )
                    
                
                    
                    # Extract relevant information from the search results
                    hospitals = [result.payload for result in search_results]
                    

                    
                    return hospitals

                # Example usage
                city = city  # Replace with the city you're interested in
                query_text = hospital_name  # Replace with your query text

                search_results = search_hospitals_by_city(city, query_text)
                search_results = search_results[0]
                st.write(f"Hospital Name: {search_results['HOSPITAL NAME']}")
                st.write(f"City: {search_results['CITY']}")
                st.write(f"Adress: {search_results['ADDRESS']}")
                adress = search_results['ADDRESS']
                st.write(f"Contact: {search_results['CONTACT']}")

            elif country == "India":
                collection_name = "Indian-Hospitals"
                # Search for hospitals based on city and query text
                def search_hospitals_by_city(city: str, query_text: str, limit=1):
                    # Convert query text to embedding
                    query_embedding = model.encode(query_text).tolist()
                    city = city.capitalize()
                    # Define the filter for the city
                    city_filter = models.Filter(
                        must=[
                            models.FieldCondition(
                                key="City",  # Make sure this matches your dataset's field name exactly
                                match=models.MatchValue(value=city)
                            )
                        ]
                    )
                    
                    # Search for similar vectors within the filtered city
                    search_results = qdrant_client.search(
                        collection_name=collection_name,
                        query_vector=query_embedding,
                        limit=limit,
                        query_filter=city_filter
                    )

                    # Extract relevant information from the search results
                    hospitals = [result.payload for result in search_results]
                    
                    return hospitals

                # Example usage
                city = city  # Replace with the correct city name
                query_text = hospital_name # Replace with your query text

                search_results = search_hospitals_by_city(city, query_text)
                search_results = search_results[0]
                st.write(f"Hospital Name: {search_results['Hospital']}")
                st.write(f"State: {search_results['State']}")
                st.write(f"City: {search_results['City']}")
                st.write(f"Adress: {search_results['LocalAddress']}")
                adress = search_results['LocalAddress']


            else:
                # Define the collection name
                collection_name = "America-Hospitals"

                # Search for hospitals based on city and query text
                def search_hospitals_by_city(city: str, query_text: str, limit=1):
                    # Convert query text to embedding
                    query_embedding = model.encode(query_text).tolist()
                    city = city.upper()
                    # Define the filter for the city
                    city_filter = models.Filter(
                        must=[
                            models.FieldCondition(
                                key="CITY",
                                match=models.MatchValue(value=city)
                            )
                        ]
                    )
                    
                    # Search for similar vectors within the filtered city
                    search_results = qdrant_client.search(
                        collection_name=collection_name,
                        query_vector=query_embedding,  # Corrected argument name
                        limit=limit,
                        query_filter=city_filter  # Using 'query_filter' to filter by city
                    )
                    
                
                    
                    # Extract relevant information from the search results
                    hospitals = [result.payload for result in search_results]
                    

                    
                    return hospitals

                # Example usage
                city = city  # Replace with the city you're interested in
                query_text = hospital_name # Replace with your query text

                search_results = search_hospitals_by_city(city, query_text)
                search_results = search_results[0]
                st.write(f"** HOSPITAL NAME:** {search_results['NAME']}")
                st.write(f"**ADDRESS:** {search_results['ADDRESS']}")
                adress = search_results['ADDRESS']
                st.write(f"**CITY:** {search_results['CITY']}")
                st.write(f"**STATE:** {search_results['STATE']}")
                st.write(f"**TELEPHONE:** {search_results['TELEPHONE']}")
                st.write(f"**TYPE:** {search_results['TYPE']}")
                st.write(f"**STATUS:** {search_results['STATUS']}")
                st.write(f"**WEBSITE:** {search_results['WEBSITE']}")
                st.write(f"**OWNER:** {search_results['OWNER']}")
                st.write(f"**BEDS:** {search_results['BEDS']}")
                st.write(f"**SOURCE:** {search_results['SOURCE']}")

            start_location_name = location
            end_location_name = adress

            if start_location_name and end_location_name:
                start_coordinates = get_location_coordinates(start_location_name)
                end_coordinates = get_location_coordinates(end_location_name)
                
                if start_coordinates and end_coordinates:
                    start_lat, start_lon = start_coordinates
                    end_lat, end_lon = end_coordinates
                    
                    st.success(f"Start Coordinates: {start_lat}, {start_lon}")
                    st.success(f"End Coordinates: {end_lat}, {end_lon}")
                    
                    map = create_map_with_route(start_lat, start_lon, end_lat, end_lon)
                    if map:
                        folium_static(map)
                else:
                    st.warning("One or both locations not found. Please try different locations.")
            else:
                st.warning("Please enter both start and end locations.")


    




     with tab[1]:  # First Aid Chatbot tab
            chat_interface()
    else:
        tabs = [ "Login","Sign Up"]
        tab = st.tabs(tabs)

        with tab[1]:  # Sign Up tab
            st.subheader("Create a New Account")

            email = st.text_input("Email", placeholder="Enter your email")
            password = st.text_input("Password", type="password", placeholder="Enter a strong password")

            if st.button("Sign Up"):
                if not validate_email(email):
                    st.error("Invalid email. Please enter a valid email address.")
                elif not validate_password(password):
                    st.error("Password must be at least 8 characters long.")
                elif email_exists(email):
                    st.error("This email is already registered. Please use another one.")
                else:
                    add_user_to_csv(email, password)
                    st.success("You have successfully signed up!")
                    st.info("Now, please login.")

        with tab[0]:  # Login tab
            st.subheader("Login to Your Account")

            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")

            if st.button("Login"):
                if validate_login(email, password):
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Invalid email or password")

if __name__ == "__main__":
    main()
