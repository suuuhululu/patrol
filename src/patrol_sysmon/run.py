from app import create_app

# [1단계: 실행 준비] 앱 생성 함수에서 기능별 경로를 등록한다.
app = create_app()

if __name__ == "__main__":
    # [로컬 개발 서버] 실행 후 http://127.0.0.1:5000 에서 기본 페이지를 확인한다.
    app.run(host="127.0.0.1", port=5000, debug=False)
