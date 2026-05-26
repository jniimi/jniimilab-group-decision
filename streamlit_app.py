"""
後方互換用エントリポイント

uv / pip ユーザー向けに従来通り `streamlit run streamlit_app.py` で動くようにしています。
実際のコードは main.py に集約されています。
"""

from main import main

if __name__ == "__main__":
    main()
