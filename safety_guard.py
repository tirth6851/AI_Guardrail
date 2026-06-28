import re
"""
Step 1: File I/O – Reading from an external banned.txt file instead of hardcoding
lists in your script.
Step 2: Text Standardization – Making the user's text lowercase and removing
punctuation so no one can bypass the filter using capitalization (e.g. "HACK").
Step 3: Tokenization – Splitting the user's sentence into individual words to check
against the banned list efficiently.

TODO:
  -Add list of all banned words and pharasez in banned..txt
  -make a function to strip and tokenize the input
  -make the algo to scan if the input is banned or not  
"""
def tokenization():
  user_input = [item for item in re.split(r'(\W+)', input("Please input your prompt here:").strip().casefold()) if item.strip()]
  #.strip()-> remove white space 
  #.casefold()-> make all small aphabates
  #.split()-> split to tokeniz
  return user_input

def check():
  TokenizedPromt=tokenization()
  with open("banned.txt","r") as file:
    bannedList=file.read().split()
    for word in TokenizedPromt:
      if word in bannedList:
        print("FLAGGED: Prompt is illegal")
        return
      print("sending it to LLM")


def main():
  check()

if __name__ == "__main__":
    main()



