"""Newsletter Agent - 뉴스레터 자동 생성 에이전트"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import os
from dotenv import load_dotenv

load_dotenv()


class NewsletterAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4",
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.7
        )

    def create_prompt(self):
        """뉴스레터 생성 프롬프트"""
        system_prompt = """당신은 전문 뉴스레터 작가입니다.
        주어진 주제에 대해 매력적이고 정보가 풍부한 뉴스레터를 작성합니다.
        - 명확한 제목 작성
        - 핵심 요점을 3-5개로 정리
        - 마크다운 형식 사용
        - 한국어로 작성"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{topic}"),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
        ])
        return prompt

    def generate_newsletter(self, topic: str) -> str:
        """뉴스레터 생성"""
        prompt = self.create_prompt()
        chain = prompt | self.llm
        response = chain.invoke({"topic": topic})
        return response.content

    def run(self, topic: str):
        """에이전트 실행"""
        newsletter = self.generate_newsletter(topic)
        return newsletter


if __name__ == "__main__":
    agent = NewsletterAgent()
    # 테스트
    result = agent.run("최신 AI 트렌드")
    print(result)
