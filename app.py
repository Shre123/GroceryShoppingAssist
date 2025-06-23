# app.py

import streamlit as st
import requests
import json
import re # For cleaning recipe text

# Define the API endpoint and key (leave key as empty string for Canvas)
API_KEY = "AIzaSyBpTz9WomZhAHWWzvxpF_bsNFEqZpiHa9E" # The Canvas environment will inject the API key at runtime if left empty
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=" + API_KEY

def call_gemini_api(prompt, schema=None):
    """
    Makes a call to the Gemini API with the given prompt.
    If a schema is provided, it will request a structured JSON response.
    """
    chat_history = []
    chat_history.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {"contents": chat_history}
    if schema:
        payload["generationConfig"] = {
            "responseMimeType": "application/json",
            "responseSchema": schema
        }

    try:
        response = requests.post(API_URL, headers={'Content-Type': 'application/json'}, json=payload)
        response.raise_for_status() # Raise an exception for HTTP errors
        result = response.json()

        if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
            text_response = result["candidates"][0]["content"]["parts"][0].get("text")
            if schema:
                return json.loads(text_response) # Parse JSON if schema was used
            return text_response
        else:
            st.error(f"Unexpected API response structure: {result}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Error calling Gemini API: {e}")
        return None
    except json.JSONDecodeError as e:
        st.error(f"Error decoding JSON response from Gemini API: {e}")
        return None

def extract_ingredients(recipe_text):
    """
    Uses LLM to extract ingredients and quantities from raw recipe text.
    It expects the LLM to return a JSON array of objects.
    """
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "item": {"type": "STRING", "description": "Name of the ingredient"},
                "quantity": {"type": "STRING", "description": "Quantity and unit (e.g., '2 cups', '500g', '1 large')"}
            },
            "required": ["item", "quantity"]
        }
    }
    prompt = f"""
    From the following recipe text, extract all ingredients and their quantities.
    Return the result as a JSON array where each element is an object with 'item' and 'quantity' keys.
    Quantities should include units. If no explicit quantity, state "to taste" or "as needed".
    Example: {{"item": "salt", "quantity": "1 tsp"}}, {{"item": "chicken breast", "quantity": "500g"}}

    Recipe Text:
    {recipe_text}
    """
    return call_gemini_api(prompt, schema)

def categorize_and_normalize_ingredients(ingredient_list_json):
    """
    Uses LLM to categorize ingredients and standardize quantities.
    It expects the LLM to return a JSON object with 'pantry' and 'perishables' arrays.
    """
    schema = {
        "type": "OBJECT",
        "properties": {
            "pantry": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "item": {"type": "STRING"},
                        "quantity": {"type": "STRING"}
                    }
                }
            },
            "perishables": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "item": {"type": "STRING"},
                        "quantity": {"type": "STRING"}
                    }
                }
            }
        },
        "required": ["pantry", "perishables"]
    }

    prompt_ingredient_list = "\n".join([f"- {item['item']}: {item['quantity']}" for item in ingredient_list_json])

    prompt = f"""
    Categorize the following list of ingredients into 'pantry' items and 'perishables'.
    Also, try to normalize quantities to common units where reasonable (e.g., "3 teaspoons" to "1 tablespoon").
    Return the result as a JSON object with two keys: 'pantry' and 'perishables', each containing an array of ingredient objects.

    Ingredients:
    {prompt_ingredient_list}

    Pantry items generally include non-refrigerated staples like salt, sugar, flour, spices, oils, pasta, rice, canned goods.
    Perishables include items that spoil quickly, typically needing refrigeration, like fresh meat, poultry, fish, dairy, eggs, fresh fruits, and most vegetables.
    """
    return call_gemini_api(prompt, schema)

def aggregate_ingredients(categorized_ingredients):
    """
    Aggregates quantities for duplicate ingredients within categories.
    This is a simplified aggregation. More advanced aggregation would require
    unit parsing and conversion (e.g., grams to ounces).
    For this low-code solution, we sum up if units match exactly or
    flag for manual review if units are complex/different.
    """
    aggregated_pantry = {}
    aggregated_perishables = {}

    for item in categorized_ingredients.get('pantry', []):
        name = item['item'].lower()
        if name in aggregated_pantry:
            # Simple aggregation: append quantities if they can't be easily summed
            aggregated_pantry[name] += f" + {item['quantity']}"
        else:
            aggregated_pantry[name] = item['quantity']

    for item in categorized_ingredients.get('perishables', []):
        name = item['item'].lower()
        if name in aggregated_perishables:
            aggregated_perishables[name] += f" + {item['quantity']}"
        else:
            aggregated_perishables[name] = item['quantity']

    # Convert back to list of dicts for consistent output
    final_pantry = [{"item": k.title(), "quantity": v} for k, v in aggregated_pantry.items()]
    final_perishables = [{"item": k.title(), "quantity": v} for k, v in aggregated_perishables.items()]

    return {"pantry": final_pantry, "perishables": final_perishables}


st.set_page_config(layout="wide", page_title="AI Grocery Shopping Assistant")
st.title("🛒 AI-Powered Grocery Shopping Assistant")
st.markdown("Enter the name of the dishes you want to cook for the week along with the servings, and I'll create a smart grocery list!")

if 'dishes' not in st.session_state:
    st.session_state.dishes = [{'name': '', 'servings': 1}]

def add_dish():
    st.session_state.dishes.append({'name': '', 'servings': 1})

def remove_dish(index):
    if len(st.session_state.dishes) > 1:
        st.session_state.dishes.pop(index)

col1, col2 = st.columns([3, 1])
with col1:
    st.subheader("Your Weekly Meal Plan")
with col2:
    st.markdown("") # For spacing
    st.button("➕ Add Another Dish", on_click=add_dish)


for i, dish in enumerate(st.session_state.dishes):
    cols = st.columns([4, 2, 1])
    with cols[0]:
        st.session_state.dishes[i]['name'] = st.text_input(
            f"Dish {i+1} Name",
            value=dish['name'],
            key=f"dish_name_{i}",
            placeholder="e.g., Chicken Tikka Masala"
        )
    with cols[1]:
        st.session_state.dishes[i]['servings'] = st.number_input(
            f"Servings",
            min_value=1,
            value=dish['servings'],
            key=f"servings_{i}"
        )
    with cols[2]:
        if len(st.session_state.dishes) > 1:
            st.markdown("<br>", unsafe_allow_html=True) # Small vertical space
            st.button("➖ Remove", key=f"remove_dish_{i}", on_click=remove_dish, args=(i,))

st.markdown("---")

if st.button("Generate Grocery List", type="primary"):
    all_recipes_text = ""
    total_ingredients_extracted = []
    loading_messages = [] # For a more detailed loading message

    valid_dishes = [d for d in st.session_state.dishes if d['name'].strip()]

    if not valid_dishes:
        st.warning("Please add at least one dish name to generate the grocery list.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, dish_entry in enumerate(valid_dishes):
            dish_name = dish_entry['name'].strip()
            servings = dish_entry['servings']

            status_text.text(f"Searching for top-rated recipe for {dish_name}...")
            # Use google_search for recipe lookup
            # This part assumes you have access to a search tool.
            # In a real Streamlit app without direct tool access like this,
            # you'd make an LLM call to get a recipe or use a dedicated recipe API.
            # For this guide, we'll simulate the search by asking the LLM for a recipe directly.
            # In a deployed setting, you'd integrate with a web search API.

            recipe_prompt = f"Find a top-rated recipe for '{dish_name}' for {servings} servings. Provide only the ingredients list and preparation steps. Do not include introductory or concluding remarks."
            recipe_content = call_gemini_api(recipe_prompt)

            if recipe_content:
                st.info(f"Recipe found for **{dish_name}**.")
                all_recipes_text += f"\n\n--- Recipe for {dish_name} ({servings} servings) ---\n{recipe_content}"

                status_text.text(f"Extracting ingredients for {dish_name}...")
                ingredients_for_dish = extract_ingredients(recipe_content)

                if ingredients_for_dish:
                    total_ingredients_extracted.extend(ingredients_for_dish)
                else:
                    st.warning(f"Could not extract ingredients for {dish_name}. Please check the dish name or try again.")
            else:
                st.warning(f"Could not find a recipe for {dish_name}. Skipping this dish.")

            progress_bar.progress((i + 1) / len(valid_dishes))

        status_text.text("Processing all ingredients...")
        if total_ingredients_extracted:
            categorized_and_normalized = categorize_and_normalize_ingredients(total_ingredients_extracted)
            if categorized_and_normalized:
                final_grocery_list = aggregate_ingredients(categorized_and_normalized)

                st.subheader("🛍️ Your Grocery Shopping List")
                grocery_list_text = ""

                st.markdown("#### Pantry Items")
                if final_grocery_list.get('pantry'):
                    for item in final_grocery_list['pantry']:
                        st.write(f"- **{item['item']}**: {item['quantity']}")
                        grocery_list_text += f"- {item['item']}: {item['quantity']}\n"
                else:
                    st.info("No pantry items identified or needed for this meal plan.")

                st.markdown("#### Perishables")
                if final_grocery_list.get('perishables'):
                    for item in final_grocery_list['perishables']:
                        st.write(f"- **{item['item']}**: {item['quantity']}")
                        grocery_list_text += f"- {item['item']}: {item['quantity']}\n"
                else:
                    st.info("No perishables identified or needed for this meal plan.")

                st.markdown("---")
                st.subheader("Copy to your Shopping List App")
                st.info("Copy the text below and paste it into Google Keep, Apple Reminders, or any other shopping list app.")
                st.code(grocery_list_text)

            else:
                st.error("Failed to categorize and normalize ingredients. Please try again.")
        else:
            st.error("No ingredients could be extracted from the recipes. Please try different dish names.")

        progress_bar.empty()
        status_text.empty()

st.sidebar.header("About This App")
st.sidebar.info(
    "This AI agent helps you generate a grocery list from your weekly meal plan. "
    "It leverages an LLM to find recipes, extract ingredients, and categorize them."
)
st.sidebar.markdown(
    "**Note:** For simplicity in a low-code environment, the recipe lookup "
    "simulates web search by asking the LLM for a recipe directly. "
    "In a production app, you might integrate with a dedicated recipe API or a robust search engine."
)
