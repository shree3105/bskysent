import logging
import sys
import os

# Add path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bsky-sentiment', 'processing'))

from models import LocalModels

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_llama_accuracy():
    models = LocalModels()
    
    print(f"\n{'='*20} TESTING LLAMA ACCURACY {'='*20}")
    
    pairs = [
        (
            "West Virginia Governor Confirms 2 National Guard Members Killed",
            "NEW: The governor of West Virginia says that two members of the state National Guard shot today in DC have died.",
            True # Expected Match
        ),
        (
            "FBI Dir. Patel Reports 2 National Guard Members in Critical Condition Attacked",
            "WASHINGTON D.C. MAYOR: ONE INDIVIDUAL WHO APPEARED TO TARGET GUARDSMEN IS IN CUSTODY",
            True # Expected Match (Same event context)
        ),
        (
            "Trump Requests 500 Troops for Washington D.C. Security Boost",
            "HEGSETH SAYS TRUMP HAS ASKED FOR 500 ADDITIONAL TROOPS TO BE DEPLOYED TO WASHINGTON, D.C.",
            True # Expected Match
        ),
        (
            "Apple stock hits all time high",
            "Tesla stock hits all time high",
            False # Expected NO Match
        )
    ]

    for text1, text2, expected in pairs:
        print(f"\nText 1: {text1}")
        print(f"Text 2: {text2}")
        
        # Run Llama Verification
        print("Asking Llama...")
        is_match = models.verify_match_llama(text1, text2)
        
        result_text = "MATCH" if is_match == expected else "FAIL"
        print(f"Llama Result: {is_match} | Expected: {expected} -> {result_text}")

if __name__ == "__main__":
    test_llama_accuracy()
