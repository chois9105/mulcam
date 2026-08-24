"""이메일 유틸리티 - 뉴스레터 배송 및 관리"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
import os
from dotenv import load_dotenv

load_dotenv()


class EmailService:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")

    def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        is_html: bool = True
    ) -> bool:
        """단일 이메일 발송"""
        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = recipient

            if is_html:
                message.attach(MIMEText(body, "html"))
            else:
                message.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)

            return True
        except Exception as e:
            print(f"이메일 발송 실패: {e}")
            return False

    def send_newsletter(
        self,
        recipients: List[str],
        subject: str,
        newsletter_html: str,
        batch_size: int = 50
    ) -> dict:
        """뉴스레터 배송"""
        results = {
            "success": 0,
            "failed": 0,
            "failed_recipients": []
        }

        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i + batch_size]
            for recipient in batch:
                if self.send_email(recipient, subject, newsletter_html):
                    results["success"] += 1
                else:
                    results["failed"] += 1
                    results["failed_recipients"].append(recipient)

        return results

    def validate_email(self, email: str) -> bool:
        """이메일 형식 검증"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None


class EmailTemplate:
    @staticmethod
    def create_newsletter_html(
        title: str,
        content: str,
        footer: str = None
    ) -> str:
        """뉴스레터 HTML 템플릿"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                .footer {{ background-color: #f0f0f0; padding: 10px; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{title}</h1>
                </div>
                <div class="content">
                    {content}
                </div>
                <div class="footer">
                    {footer or "© 2024 Newsletter"}
                </div>
            </div>
        </body>
        </html>
        """
        return html
