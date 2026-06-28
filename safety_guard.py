from dotenv import load_dotenv
from groq import Groq
import os
import re
"""
Step 1: File I/O – Reading from an external banned.txt file instead of hardcoding
lists in your script.
Step 2: Text Standardization – Making the user's text lowercase and removing
punctuation so no one can bypass the filter using capitalization (e.g. "HACK").
Step 3: Tokenization – Splitting the user's sentence into individual words to check
against the banned list efficiently.

# NOTE: There is an error in this file - 'pharasez' on line 11 should 
# be 'phrases' and additionaly there is a logic error in the check function: "There is a logic error in this loop. 
Because print("sending it to LLM") is inside the for loop, it will execute for every single safe word in the prompt. 
If a user types 5 safe words, it will print this message 5 times.To fix this, move the success message completely outside 
and below the for loop so it only runs after all words have been verified."


TODO:
  -Add list of all banned words and pharasez in banned..txt
  -make a function to strip and tokenize the input
  -make the algo to scan if the input is banned or not  
"""
load_dotenv()
key = os.getenv("GROQ_API_KEY")
client=Groq(api_key=key)
user_input=None
def tokenization():
  global user_input
  user_input = input("Please input your prompt here:").strip().casefold()
  return [item for item in re.split(r'(\W+)', user_input) if item.strip()]

TokenizedPromt=tokenization()
def promtVerification():
  with open("banned.txt","r") as file:
    bannedList=file.read().split()
    for word in TokenizedPromt:
      if word in bannedList:
        print("FLAGGED: Prompt is illegal")
        return False
  print("sending it to LLM")
  return True

def main():
  if promtVerification() is True:
    LLMrequest()



def LLMrequest():
  responce = client.chat.completions.create(
    model = "llama-3.3-70b-versatile",
    messages= [{"role": "user", "content": user_input}]
  )
  print(responce.choices[0].message.content)




if __name__ == "__main__":
  main()



