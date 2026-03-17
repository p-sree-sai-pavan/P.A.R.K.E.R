from langchain_classic.memory import ConversationBufferMemory
from langchain_classic.chains import ConversationChain
from langchain_ollama.llms import OllamaLLM

llm = OllamaLLM(model="qwen2.5:7b")
memory = ConversationBufferMemory()

chain = ConversationChain(
    llm=llm,
    memory=memory,
    verbose=True
)

def ask(question):
    response = chain.predict(input = question)
    return response
