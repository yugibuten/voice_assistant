import openai

# Set your OpenAI API key
openai.api_key = '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'

def chat_with_gpt(prompt):
    response = openai.Completion.create(
        engine='text-davinci-003',
        prompt=prompt,
        max_tokens=100,
        temperature=0.7,
        n = 1,
        stop=None,
        response_format="json"
    )

    # Extract the generated text from the response
    generated_text = response.choices[0].text.strip()

    return generated_text

# Example usage
user_input = input("You: ")

while user_input.lower() != 'bye':
    # Append user input to the prompt
    prompt = f"You: {user_input}\nAI:"

    # Get response from the chatbot
    response = chat_with_gpt(prompt)

    print("AI:", response)
    user_input = input("You: ")



def wishme():
   hour = int(datetime.datetime.now().hour)


   temperature = asyncio.run(getweather())
            speak("The current temperature is {} degree farenhite".format(temperature)) 