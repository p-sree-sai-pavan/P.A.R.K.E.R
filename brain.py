from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

model = OllamaLLM(model="qwen2.5:7b")
template = """You are a helpful AI assistant. Answer the user's question using the conversation history if it is relevant.
Chat History: {history}
Current Question: {question}
Provide a clear and concise answer.
"""

prompt = ChatPromptTemplate.from_template(template)

chain = prompt | model

def ask(question):
    result = chain.invoke({"question": question})
    return result

