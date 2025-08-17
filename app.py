import streamlit as st
import pandas as pd
import sqlite3

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="Food Donation Insights", layout="wide")
st.title("🍽️ Food Donation Insights & Management")

st.markdown(
    """
    <style>
    div[data-testid="metric-container"] {
        background: #f0f8ff;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    }
    </style>
    """,
    unsafe_allow_html=True
)


# -----------------------------
# DB helpers
# -----------------------------
@st.cache_resource
def get_conn():
    return sqlite3.connect("food_donation.db", check_same_thread=False)

def run_query(sql, params=None):
    conn = get_conn()
    return pd.read_sql_query(sql, conn, params=params or [])

def execute(sql, params=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params or [])
    conn.commit()

# -----------------------------
# Sidebar Filters (City, Provider, Food Type, Meal Type)
# -----------------------------
st.sidebar.header("Filters")

# City options (from Providers; we join Listings->Providers for city)
cities = run_query("SELECT DISTINCT City FROM Providers ORDER BY City")["City"].dropna().tolist()
city = st.sidebar.selectbox("City", ["(All)"] + cities)

# Provider options (by selected city if any)
if city == "(All)":
    providers = run_query("SELECT Provider_ID, Name FROM Providers ORDER BY Name")
else:
    providers = run_query(
        "SELECT Provider_ID, Name FROM Providers WHERE City = ? ORDER BY Name",
        [city],
    )
provider_map = {f"{row['Name']} (ID {row['Provider_ID']})": row["Provider_ID"] for _, row in providers.iterrows()}
provider_choice = st.sidebar.selectbox("Provider", ["(All)"] + list(provider_map.keys()))

# Food type options
food_types = run_query("SELECT DISTINCT Food_Type FROM Food_Listings ORDER BY Food_Type")["Food_Type"].dropna().tolist()
food_type = st.sidebar.selectbox("Food Type", ["(All)"] + food_types)

# Meal type options (if your dataset has Meal_Type; if not, this will be empty and harmless)
meal_types = run_query("SELECT DISTINCT Meal_Type FROM Food_Listings WHERE Meal_Type IS NOT NULL ORDER BY Meal_Type")
meal_list = meal_types["Meal_Type"].tolist()
meal_type = st.sidebar.selectbox("Meal Type", ["(All)"] + meal_list)

# Build listings base query with filters (join providers to get city)
base_sql = """
SELECT
  F.Food_ID,
  P.Name AS Provider_Name,
  P.City,
  F.Food_Type,
  COALESCE(F.Meal_Type, '-') AS Meal_Type,
  F.Quantity,
  DATE(F.Expiry_Date) AS Expiry_Date
FROM Food_Listings F
JOIN Providers P ON F.Provider_ID = P.Provider_ID
WHERE 1=1
"""
params = []
if city != "(All)":
    base_sql += " AND P.City = ?"
    params.append(city)
if provider_choice != "(All)":
    base_sql += " AND P.Provider_ID = ?"
    params.append(provider_map[provider_choice])
if food_type != "(All)":
    base_sql += " AND F.Food_Type = ?"
    params.append(food_type)
if meal_type != "(All)":
    base_sql += " AND F.Meal_Type = ?"
    params.append(meal_type)
base_sql += " ORDER BY Expiry_Date ASC"

# -----------------------------
# Sidebar Navigation
# -----------------------------
menu = st.sidebar.radio(
    "Navigation",
    ["🔎 Explore Listings", "📇 Contacts", "🧮 Queries", "🛠️ CRUD"]
)

if menu == "🔎 Explore Listings":
    st.subheader("Filtered Food Listings")
    df_listings = run_query(base_sql, params)
    st.dataframe(df_listings, use_container_width=True)

    # KPIs
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Listings", len(df_listings))
    if not df_listings.empty and "Quantity" in df_listings.columns:
        c2.metric("Total Quantity", int(df_listings["Quantity"].sum()))
    else:
        c2.metric("Total Quantity", 0)
    if not df_listings.empty and "Expiry_Date" in df_listings.columns:
        c3.metric("Nearest Expiry", df_listings["Expiry_Date"].min())
    else:
        c3.metric("Nearest Expiry", "N/A")

elif menu == "📇 Contacts":

    st.subheader("Provider Contact Details")
    city_filter = st.selectbox("Filter by City (optional)", ["(All)"] + cities, key="contacts_city")
    if city_filter == "(All)":
        prov_contacts = run_query("SELECT Name, City, Contact FROM Providers ORDER BY City, Name")
    else:
        prov_contacts = run_query("SELECT Name, City, Contact FROM Providers WHERE City = ? ORDER BY Name", [city_filter])
    st.dataframe(prov_contacts, use_container_width=True)

    st.markdown("---")
    st.subheader("Receiver Contact Details")
    # Assuming Receivers table has Name, City, Contact (adapt if your column names differ)
    if city_filter == "(All)":
        rec_contacts = run_query("SELECT Name, City, Contact FROM Receivers ORDER BY City, Name")
    else:
        rec_contacts = run_query("SELECT Name, City, Contact FROM Receivers WHERE City = ? ORDER BY Name", [city_filter])
    st.dataframe(rec_contacts, use_container_width=True)

elif menu == "🧮 Queries":

    st.subheader("Run Predefined SQL Queries")

    # Dictionary storing all queries
    queries = {
        "1. Total Providers & Receivers per City": """
            SELECT City, 
                    (SELECT COUNT(*) FROM Providers p WHERE p.City = c.City) AS Total_Providers,
                    (SELECT COUNT(*) FROM Receivers r WHERE r.City = c.City) AS Total_Receivers
            FROM (SELECT City FROM Providers UNION SELECT City FROM Receivers) c
            GROUP BY City
            ORDER BY City;
        """,
        "2. Top Food Providers by Contribution": """
            SELECT Type AS Provider_Type, COUNT(*) AS Total_Contributions
            FROM Providers p
            JOIN Food_Listings f ON p.Provider_ID = f.Provider_ID
            GROUP BY Type
            ORDER BY Total_Contributions DESC;
        """,
        "3. Contact Info of Providers in a City": """
            SELECT Name, Contact
            FROM Providers
            WHERE City = ?;
        """,
        "4. Receivers with Most Claims": """
            SELECT r.Receiver_ID, COUNT(c.Claim_ID) AS Total_Claims
            FROM Receivers r
            JOIN Claims c ON r.Receiver_ID = c.Receiver_ID
            GROUP BY r.Receiver_ID
            ORDER BY Total_Claims DESC
            LIMIT 10;
        """,
        "5. Total Quantity of Food Available": """
            SELECT SUM(Quantity) AS Total_Food_Quantity
            FROM Food_Listings;
        """,
        "6. City with Highest Food Listings": """
            SELECT p.City, COUNT(f.Food_ID) AS Total_Listings
            FROM Food_Listings f
            JOIN Providers p ON f.Provider_ID = p.Provider_ID
            GROUP BY p.City
            ORDER BY Total_Listings DESC
            LIMIT 1;
        """,
        "7. Most Common Food Types": """
            SELECT Food_Type, COUNT(*) AS Total_Listings
            FROM Food_Listings
            GROUP BY Food_Type
            ORDER BY Total_Listings DESC
            LIMIT 10;
        """,
        "8. Claims per Food Type": """
            SELECT F.Food_Type, COUNT(C.Claim_ID) AS Total_Claims
            FROM Claims C
            JOIN Food_Listings F USING(Food_ID)
            GROUP BY F.Food_Type
            ORDER BY Total_Claims DESC;
        """,
        "9. Provider with Most Successful Claims": """
            SELECT P.Name, COUNT(C.Claim_ID) AS Successful_Claims
            FROM Claims C
            JOIN Food_Listings F USING(Food_ID)
            JOIN Providers P USING(Provider_ID)
            WHERE C.Status = 'Completed'
            GROUP BY P.Name
            ORDER BY Successful_Claims DESC
            LIMIT 1;
        """,
        "10. Percentage of Completed, Pending, Cancelled Claims": """
            SELECT Status,
                ROUND(100.0 * COUNT(Claim_ID)/ (SELECT COUNT(*) FROM Claims),1) AS Percentage
            FROM Claims
            GROUP BY Status;
        """,
        "11. Average Quantity Claimed per Receiver": """
            SELECT r.Receiver_ID, AVG(f.Quantity) AS Avg_Quantity_Claimed
            FROM Claims c
            JOIN Food_Listings f ON c.Food_ID = f.Food_ID
            JOIN Receivers r ON c.Receiver_ID = r.Receiver_ID
            GROUP BY r.Receiver_ID
            ORDER BY Avg_Quantity_Claimed DESC
            LIMIT 10;
        """,
        "12. Most Claimed Meal Type": """
            SELECT F.Meal_Type, COUNT(C.Claim_ID) AS Total_Claims
            FROM Claims C
            JOIN Food_Listings F ON C.Food_ID = F.Food_ID
            GROUP BY F.Meal_Type
            ORDER BY Total_Claims DESC
            LIMIT 1;
        """,
        "13. Total Quantity Donated by Each Provider": """
            SELECT P.Name, SUM(F.Quantity) AS Total_Donated
            FROM Food_Listings F
            JOIN Providers P USING(Provider_ID)
            GROUP BY P.Name
            ORDER BY Total_Donated DESC
            LIMIT 10;
        """,
        "14. Top Food Providers by Total Contributions": """
            SELECT Provider_ID, Name, COUNT(Food_ID) AS Total_Contributions
            FROM Food_Listings
            JOIN Providers USING(Provider_ID)
            GROUP BY Provider_ID, Name
            ORDER BY Total_Contributions DESC
            LIMIT 10;
        """,
        "15. Highest Demand Locations based on Food Claims": """
            SELECT P.City, COUNT(C.Claim_ID) AS Total_Claims
            FROM Claims C
            JOIN Food_Listings F USING(Food_ID)
            JOIN Providers P USING(Provider_ID)
            GROUP BY P.City
            ORDER BY Total_Claims DESC
            LIMIT 10;
        """
    }

    chosen = st.selectbox("Choose a query to run", list(queries.keys()))
    param_needed = (chosen.startswith("3."))

    params_q = []
    if param_needed:
        city_for_contacts = st.text_input("Enter City (exact match)", "")
        if st.button("Run Query"):
            if not city_for_contacts.strip():
                st.warning("Please enter a city name.")
            else:
                dfq = run_query(queries[chosen], [city_for_contacts.strip()])
                st.dataframe(dfq, use_container_width=True)
    else:
        if st.button("Run Query"):
            dfq = run_query(queries[chosen])
            st.dataframe(dfq, use_container_width=True)

elif menu == "🛠️ CRUD":

    st.subheader("Manage Data (CRUD)")

    crud_tabs = st.tabs(["➕ Create", "✏️ Update", "🗑️ Delete"])

    # --- Create ---
    with crud_tabs[0]:
        st.markdown("#### Create Provider")
        with st.form("create_provider"):
            c_id = st.number_input("Provider_ID (int)", min_value=1, step=1)
            c_name = st.text_input("Name")
            c_type = st.text_input("Type")
            c_addr = st.text_area("Address")
            c_city = st.text_input("City")
            c_contact = st.text_input("Contact")
            submitted = st.form_submit_button("Create Provider")
        if submitted:
            try:
                execute(
                    "INSERT INTO Providers (Provider_ID, Name, Type, Address, City, Contact) VALUES (?, ?, ?, ?, ?, ?)",
                    [c_id, c_name, c_type, c_addr, c_city, c_contact],
                )
                st.success("Provider created.")
            except sqlite3.IntegrityError as e:
                st.error(f"Failed: {e}")

        st.markdown("---")
        st.markdown("#### Create Food Listing")
        with st.form("create_listing"):
            f_id = st.number_input("Food_ID (int)", min_value=1, step=1)
            f_provider = st.number_input("Provider_ID (must exist)", min_value=1, step=1)
            f_type = st.selectbox("Food_Type", food_types) if food_types else st.text_input("Food_Type")
            f_meal = st.selectbox("Meal_Type (optional)", ["", *meal_list]) if meal_list else st.text_input("Meal_Type (optional)")
            f_qty = st.number_input("Quantity", min_value=1, step=1)
            f_exp = st.date_input("Expiry_Date")
            submitted2 = st.form_submit_button("Create Listing")
        if submitted2:
            try:
                execute(
                    "INSERT INTO Food_Listings (Food_ID, Provider_ID, Food_Type, Meal_Type, Quantity, Expiry_Date) VALUES (?, ?, ?, ?, ?, ?)",
                    [f_id, f_provider, f_type, (f_meal or None), f_qty, str(f_exp)],
                )
                st.success("Food listing created.")
            except sqlite3.IntegrityError as e:
                st.error(f"Failed: {e}")

    # --- Update ---
    with crud_tabs[1]:
        st.markdown("#### Update Provider Name")
        with st.form("update_provider"):
            up_id = st.number_input("Provider_ID", min_value=1, step=1)
            up_name = st.text_input("New Name")
            up_submit = st.form_submit_button("Update Provider")
        if up_submit:
            execute("UPDATE Providers SET Name = ? WHERE Provider_ID = ?", [up_name, up_id])
            st.success("Provider updated (if ID existed).")

        st.markdown("---")
        st.markdown("#### Update Listing Quantity")
        with st.form("update_listing"):
            ul_id = st.number_input("Food_ID", min_value=1, step=1)
            ul_qty = st.number_input("New Quantity", min_value=0, step=1)
            ul_submit = st.form_submit_button("Update Listing")
        if ul_submit:
            execute("UPDATE Food_Listings SET Quantity = ? WHERE Food_ID = ?", [ul_qty, ul_id])
            st.success("Listing updated (if Food_ID existed).")

    # --- Delete ---
    with crud_tabs[2]:
        st.markdown("#### Delete Provider (be careful!)")
        with st.form("delete_provider"):
            dp_id = st.number_input("Provider_ID to delete", min_value=1, step=1)
            dp_submit = st.form_submit_button("Delete Provider")
        if dp_submit:
            try:
                execute("DELETE FROM Providers WHERE Provider_ID = ?", [dp_id])
                st.success("Provider deleted (if ID existed).")
            except sqlite3.IntegrityError as e:
                st.error(f"Failed (possible FK constraints): {e}")

        st.markdown("---")
        st.markdown("#### Delete Food Listing")
        with st.form("delete_listing"):
            dl_id = st.number_input("Food_ID to delete", min_value=1, step=1)
            dl_submit = st.form_submit_button("Delete Listing")
        if dl_submit:
            execute("DELETE FROM Food_Listings WHERE Food_ID = ?", [dl_id])
            st.success("Listing deleted (if Food_ID existed).")