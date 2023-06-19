import pyttsx3
import datetime
import requests, json
import python_weather
import wolframalpha
import time

import asyncio
import os
import openai
# import speechRecognition as sr
import speech_recognition as sr
import wikipedia
import pyjokes
from urllib.request import urlopen



  


engine = pyttsx3.init('sapi5')
voices = engine.getProperty('voices') #gets you the details of the current voice
engine.setProperty('voice', voices[1].id)  # 0-male voice , 1-female voice




async def getweather(city_name):
  # declare the client. the measuring unit used defaults to the metric system (celcius, km/h, etc.)
  async with python_weather.Client(unit=python_weather.IMPERIAL) as client:
    # fetch a weather forecast from a city
    weather = await client.get(city_name)
    
    # returns the current day's forecast temperature (int)
    temperature = weather.current.temperature
    return temperature


def speak(audio):   
    engine.say(audio)    
    engine.runAndWait() #Without this command, speech will not be audible to u



def wishMe():
    hour = int(datetime.datetime.now().hour)
    if hour>=0 and hour<12:
        speak("Good Morning!")    
    
    elif hour>=12 and hour<18:
        speak("Good Afternoon!")       
    
    else:
        speak("Good Evening!")      
   
    speak('Hello, I am Friday. Please tell me how may I help you')

def takeCommand():
    #It takes microphone input from the user and returns string output    
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        r.pause_threshold = 1
        audio = r.listen(source)

    try:
        print("Recognizing...")    
        query = r.recognize_google(audio, language='en-in') #Using google for voice recognition.
        print(f"User said: {query}\n")  #User query will be printed.    
    except Exception as e:
        # print(e)  use only if you want to print the error!
        print("Say that again please...")   #Say that again will be printed in case of improper voice 
        return "None" #None string will be returned
    
    return query



if __name__=="__main__" :
    
    
    # weather()
    # wishMe()
    # takeCommand()
    while True:
        query = takeCommand().lower() #Converting user query into lower case
        if "hey friday" in query:
            wishMe()
            break
    while True:
        query = takeCommand().lower() #Converting user query into lower case        
        # Logic for executing tasks based on query
        if 'wikipedia' in query:  #if wikipedia found in the query then this block will be executed
            speak('Searching Wikipedia...')
            query = query.replace("wikipedia", "")
            results = wikipedia.summary(query, sentences=2) 
            speak("According to Wikipedia")
            speak(results)
        elif 'who is ' in query:
            query = query.replace("who is", "")
            results = wikipedia.summary(query, sentences=1) 
            speak(results)

        elif 'how are you' in query:
            speak("I am fine, Thank you")
            speak("How are you")
          
 
        elif 'fine' in query or "good" in query:
            speak("It's good to know that your fine")

        elif 'joke' in query:
            speak(pyjokes.get_joke())

        elif 'play music' in query:
            music_dir = ''
            music_name = query.split(' ')[-1] + '.mp3'
            os.startfile(os.path.join(music_dir, music_name))
        elif 'time' in query:
            strTime = datetime.datetime.now().strftime("%H:%M:%S")    
            speak(f"The time is {strTime}")
        elif "calculate" in query:
             
            app_id = "9KJPY9-8UX3UWRLU7"
            client = wolframalpha.Client(app_id)
            indx = query.lower().split().index('calculate')
            query = query.split()[indx + 1:]
            res = client.query(' '.join(query))
            answer = next(res.results).text
            print("The answer is " + answer)
            speak("The answer is " + answer)
        elif "what is" in query or "who is" in query:
             
            # Use the same API key
            # that we have generated earlier
            client = wolframalpha.Client("9KJPY9-8UX3UWRLU7")
            res = client.query(query)
             
            try:
                print (next(res.results).text)
                speak (next(res.results).text)
            except StopIteration:
                print ("No results")    

        elif 'weather' in query:
            speak(" City name ")
            print("City name : ")
            city_name = takeCommand()
            temperature = asyncio.run(getweather(city_name))
            speak("The current temperature is {} degree farenhite".format(temperature)) 
            
        elif 'bye' in query:
            speak('I will be back')
            exit()
        else:
            speak("I didn't get you ,can you say that again ")    