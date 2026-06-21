from app.schemas.demo import DemoData


class DemoService:
    @staticmethod
    def echo(text: str) -> DemoData:
        return DemoData(
            original_text=text,
            echoed_text=f"echo: {text}"
        )