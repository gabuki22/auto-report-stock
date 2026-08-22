# -*- coding: utf-8 -*-
"""메일 발송 — **8주차 자리 표시. 지금은 구현하지 않는다.**

왜 빈 파일을 미리 만드는가
    8주차에 *"어디에 넣어야 하지"*를 다시 찾지 않기 위해서다. 자리를 표시해두면
    그때 **이 파일만 채우면** 된다.

    ```
    오늘 (6주차)                          8주차
    파일 → … → 이메일 초안 → [확정] → ██████ → 발송
                                     여기에 SMTP를 꽂는다
    ```

★ **이 함수는 아무 데서도 호출되지 않는다.**
    `app.py`·`run_pipeline.py` 어디에도 `send.py` import가 없다. 실수로 호출되면
    `NotImplementedError`로 앱이 죽으므로, 호출 지점은 **주석으로만** 표시해 둔다
    (`app.py` 8단계 확정 블록 참고).

8주차에 필요한 것 — 이것만으로 한 회차가 필요하다
    · **앱 비밀번호** — Gmail 등은 계정 비밀번호로 SMTP 로그인이 막혀 있다.
      2단계 인증을 켜고 앱 전용 비밀번호를 발급받아야 한다.
    · **SMTP 서버 설정** — 호스트·포트(587 STARTTLS / 465 SSL)·TLS 방식.
      사내 메일이면 릴레이 서버와 방화벽 정책도 함께 본다.
    · **첨부 파일 인코딩** — `MIMEBase` + base64. 한글 파일명은 RFC 2231로 인코딩하지
      않으면 받는 쪽에서 깨진다.
    · **수신자 검증** — 주소 형식·중복·오타. **잘못 보내면 되돌릴 수 없다**(게이트 3과 같은 이유).
    · **인증 오류 처리** — 자격 증명 만료·발송 한도 초과·일시 거부(4xx)와 영구 거부(5xx)를
      구분해서 재시도 여부를 정한다.

★ 자격 증명을 코드·저장소에 두지 않는다
    환경 변수나 `.streamlit/secrets.toml`(이미 `.gitignore` 대상)에서 읽는다.
    `config.py`의 수신자도 예시값이며 실제 주소를 넣지 않는다.
"""
from __future__ import annotations


def send_email(email_meta: dict, attachments: list[dict]) -> dict:
    """확정된 이메일 초안을 실제로 발송한다 — **8주차에 구현.**

    Args:
        email_meta: `email_draft.build_email()`의 반환에서 subject·to·from·
            body_html·body_text. 확정본은 `outputs/run_*/email_final.html`에 있다.
        attachments: `[{"filename", "path", "size"}]` — 존재하는 파일만.

    Returns:
        발송 결과 `{"성공": bool, "메시지ID": str, "발송_시각": str, "실패사유": str}`.
        이 결과도 `run_log.json`에 남겨야 한다(9번째 단계 기록).

    Raises:
        NotImplementedError: 6주차 범위에서는 항상. **호출하면 안 된다.**
    """
    raise NotImplementedError(
        "메일 발송은 8주차에 구현합니다. 이 앱은 발송 준비된 최종본을 확정하는 것까지만 합니다.\n"
        "필요한 것: 앱 비밀번호 · SMTP 서버 설정 · 첨부 파일 인코딩 · "
        "수신자 검증 · 인증 오류 처리")
