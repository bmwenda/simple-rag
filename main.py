from langchain_core.prompts import ChatPromptTemplate

from src.model import get_chat_model
from src.retriever import retrieve_documents

SYSTEM_PROMPT = "You are a helpful assistance. Answer questions concisely and use only the company information as context.\n\nContext:\n{context}\nIf you don't have an answer from the context, politely guide the user to consult their manager, HR or onboarding buddy for guidance"

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "{query}")
])

llm = get_chat_model()
chain = prompt | llm

def chat(query: str) -> str:
    try:
        context = retrieve_documents(query)
        response = chain.invoke({"context": context, "query": query})
        return response.text
    except Exception as e:
        return(f"Sorry! I crapped out. Try again, or type q to exit :'(\n{str(e)}")

print("Hello new joiner! Welcome to Aetheris! Ask me any question regarding us e.g policies and other useful information.\nTo exit, type 'q', 'quit' or 'exit'")

while True:
    user_input = input("> ")
    if user_input.strip().lower() in ["q", "quit", "exit"]:
        print("See you soon!!")
        break

    print(chat(user_input))
