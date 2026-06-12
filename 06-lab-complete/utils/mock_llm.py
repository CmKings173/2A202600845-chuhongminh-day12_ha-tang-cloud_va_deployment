"""
Mock LLM — không cần API key thật.

Dùng cho local dev và lab demo. Khi có OPENAI_API_KEY thật,
thay hàm ask() bằng openai.chat.completions.create().
"""
import time
import random


_RESPONSES = {
    "docker": [
        "Container là cách đóng gói app để chạy ở mọi nơi — build once, run anywhere.",
        "Docker giải quyết vấn đề 'works on my machine' bằng cách đóng gói toàn bộ runtime.",
    ],
    "deploy": [
        "Deployment là quá trình đưa code từ máy dev lên server để người dùng truy cập được.",
        "Cloud deployment = containerize → push image → platform chạy cho bạn.",
    ],
    "redis": [
        "Redis là in-memory data store. Dùng cho caching, session, rate limiting.",
        "Redis cho phép nhiều instance chia sẻ state — cần thiết để scale ngang.",
    ],
    "security": [
        "API security bao gồm: authentication (ai được dùng), rate limiting (dùng bao nhiêu), cost guard (tốn bao nhiêu).",
    ],
    "health": [
        "Health check endpoint giúp platform biết app còn sống không để tự động restart khi cần.",
    ],
    "default": [
        "Đây là response từ mock LLM. Trong production, đây sẽ là câu trả lời từ GPT-4o-mini.",
        "Agent đang hoạt động tốt! Câu hỏi của bạn đã được nhận và xử lý.",
        "Tôi là AI agent được deploy lên cloud. Hỏi tôi về Docker, deployment, hoặc security nhé.",
    ],
}


def ask(question: str, delay: float = 0.05) -> str:
    """
    Mock LLM call. Trả về câu trả lời giả lập.

    Args:
        question: Câu hỏi của user
        delay: Giả lập API latency (giây)
    """
    time.sleep(delay + random.uniform(0, 0.05))

    q = question.lower()
    for keyword, responses in _RESPONSES.items():
        if keyword in q:
            return random.choice(responses)

    return random.choice(_RESPONSES["default"])


def ask_stream(question: str):
    """
    Mock streaming — yield từng từ để giả lập streaming response.
    """
    response = ask(question)
    for word in response.split():
        time.sleep(0.04)
        yield word + " "
