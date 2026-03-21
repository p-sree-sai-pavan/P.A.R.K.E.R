"""
app.py — Parker AI Desktop (Premium Dark, Feature-Rich)
Run:  python app.py

Features:
- Streaming markdown rendering
- Auto-resizing input area
- Copy message buttons
- Stop generation button
- New Chat button
"""

import sys
import subprocess
import threading
import webbrowser
import uuid

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea,
    QFrame, QSizePolicy, QTextEdit, QSpacerItem,
    QGraphicsDropShadowEffect, QToolButton, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import (
    QFont, QColor, QTextCursor, QIcon
)

from langchain_core.messages import SystemMessage, HumanMessage
from ears import listen
from mouth import speak

from config import DB_URI, DEFAULT_USER_ID
from database import create_store, create_checkpointer, setup_database, close_connections
from graph import build_graph

# ── Palette (Premium Dark / Zinc) ─────────────────────────────────
BG          = "#09090b"
SIDEBAR_BG  = "#09090b"
BORDER      = "#27272a"
TEXT        = "#fafafa"
TEXT_DIM    = "#a1a1aa"
USER_BG     = "#18181b"
ACCENT      = "#ffffff"
ACCENT_FG   = "#000000"
ACCENT_HOVER = "#e4e4e7"
INPUT_BG    = "#18181b"
FONT_BODY   = "Segoe UI"
FONT_MONO   = "Consolas"


# ══════════════════════════════════════════════════════════════════
#  WORKER — LLM streaming + actions
# ══════════════════════════════════════════════════════════════════
class Worker(QThread):
    token    = Signal(str)
    status   = Signal(str)
    finished = Signal(str)

    def __init__(self, graph, config: dict, prompt: str):
        super().__init__()
        self.graph   = graph
        self.config  = config
        self.prompt  = prompt
        self._full   = ""
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            p = self.prompt.lower().strip()

            if p.startswith("open "):
                self._open_app(p[5:].strip())
            elif p.startswith("search "):
                self._web_search(p[7:].strip())
            else:
                self._chat()

        except Exception as e:
            if not self._cancel:
                self.status.emit("error")
                self.token.emit(f"\n⚠ Error: {e}")
                self.finished.emit("")

    def _open_app(self, app: str):
        self.status.emit("thinking")
        try:
            subprocess.Popen(f"start {app}", shell=True)
            self._full = f"Opened {app}."
            self.token.emit(self._full)
        except Exception as e:
            self._full = f"Could not open {app}: {e}"
            self.token.emit(self._full)
        self.status.emit("done")
        self.finished.emit(self._full)

    def _web_search(self, query: str):
        self.status.emit("thinking")
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        self._full = f'Searched Google for "{query}". Browser opened.'
        self.token.emit(self._full)
        self.status.emit("done")
        self.finished.emit(self._full)

    def _chat(self):
        self.status.emit("thinking")

        # Use the graph — it handles trigger, memory retrieval/storage,
        # and chat response. The checkpointer accumulates conversation
        # history automatically across turns.
        self.status.emit("responding")

        for event in self.graph.stream(
            {"messages": [HumanMessage(content=self.prompt)]},
            self.config,
            stream_mode="messages",
        ):
            if self._cancel:
                break
            msg, metadata = event
            # Only stream tokens from the chat node (the final response)
            if metadata.get("langgraph_node") == "chat" and hasattr(msg, "content") and msg.content:
                self._full += msg.content
                self.token.emit(msg.content)

        if not self._cancel:
            self.status.emit("done")
            self.finished.emit(self._full)


class VoiceWorker(QThread):
    result = Signal(str)
    error  = Signal(str)

    def run(self):
        try:
            text = listen()
            self.result.emit(text) if text else self.error.emit("Didn't catch that.")
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════════
#  AUTO-RESIZING TEXT EDIT
# ══════════════════════════════════════════════════════════════════
class ChatInputEdit(QTextEdit):
    submit = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Message Parker... (Shift+Enter for newline)")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self.setFont(QFont(FONT_BODY, 11))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {TEXT};
                border: none;
                padding: 10px 0px;
            }}
            QTextEdit::placeholder {{ color: {TEXT_DIM}; }}
        """)
        self.setMinimumHeight(44)
        self.setMaximumHeight(200)

    def _adjust_height(self):
        doc_height = int(self.document().size().height())
        margins = self.contentsMargins()
        h = doc_height + margins.top() + margins.bottom() + 10
        self.setFixedHeight(min(max(44, h), 200))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if event.modifiers() == Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                text = self.toPlainText().strip()
                self.submit.emit(text)
        else:
            super().keyPressEvent(event)


# ══════════════════════════════════════════════════════════════════
#  CHAT MESSAGE WIDGET
# ══════════════════════════════════════════════════════════════════
class ChatMessage(QFrame):
    def __init__(self, role: str, text: str = "", parent=None):
        super().__init__(parent)
        self.role = role
        self._text = text

        is_user = role == "user"
        
        self.setStyleSheet(f"""
            QFrame {{
                background: {USER_BG if is_user else "transparent"};
                border: 1px solid {BORDER if is_user else "transparent"};
                border-radius: 12px;
                margin: {"2px 40px 2px 0px" if is_user else "2px 0px 2px 0px"};
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 8, 18, 8)
        lay.setSpacing(4)

        # Header bar
        header_lay = QHBoxLayout()
        header = QLabel("You" if is_user else "Parker")
        header.setFont(QFont(FONT_BODY, 10, QFont.Bold))
        header.setStyleSheet(f"color: {TEXT if is_user else TEXT_DIM}; border: none;")
        header_lay.addWidget(header)
        header_lay.addStretch()

        # Copy button
        self.copy_btn = QToolButton()
        self.copy_btn.setText("📋")
        self.copy_btn.setToolTip("Copy message")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent; color: {TEXT_DIM}; border: none; font-size: 14px;
            }}
            QToolButton:hover {{ color: {TEXT}; }}
        """)
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        self.copy_btn.hide() # hide until hovered (handled via enterEvent)
        header_lay.addWidget(self.copy_btn)
        
        lay.addLayout(header_lay)

        # Body
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setFrameStyle(QFrame.NoFrame)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.body.document().documentLayout().documentSizeChanged.connect(self._fit)
        
        # Markdown rendering needs rich text styling
        font = QFont(FONT_BODY, 11)
        self.body.setFont(font)
        self.body.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {TEXT};
                border: none;
                padding: 0;
            }}
        """)
        
        if text:
            self._text = text
            self.body.setMarkdown(text)
            
        lay.addWidget(self.body)

    def append_text(self, chunk: str):
        self._text += chunk
        # Streaming as plain text is smoother than constant markdown re-parsing
        # We will parse markdown when generation is completely done
        self.body.setPlainText(self._text)
        self.body.moveCursor(QTextCursor.End)

    def finalize_markdown(self):
        """Called when generation is totally done, to render markdown properly."""
        if self._text:
            self.body.setMarkdown(self._text)

    def _fit(self):
        doc = self.body.document()
        doc.setTextWidth(self.body.viewport().width())
        h = int(doc.size().height()) + 8
        self.body.setFixedHeight(max(h, 28))

    def _copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self._text)
        self.copy_btn.setText("✔")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("📋"))

    def enterEvent(self, event):
        self.copy_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.copy_btn.hide()
        super().leaveEvent(event)


# ══════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════
class ParkerApp(QWidget):
    def __init__(self, store, checkpointer):
        super().__init__()
        self.store       = store
        self.checkpointer = checkpointer
        self.graph       = build_graph(store, checkpointer)
        
        # User ID for memory namespacing
        self.user_id     = DEFAULT_USER_ID
        # Thread ID for conversation history — rotated on "New Chat"
        self.thread_id   = str(uuid.uuid4())
        
        self.worker      = None
        self._busy       = False
        self._ai_msg     = None
        self._last_input = ""

        self.setWindowTitle("Parker AI")
        self.resize(900, 800)
        self.setMinimumSize(560, 440)
        self.setStyleSheet(f"QWidget {{ background: {BG}; color: {TEXT}; font-family: '{FONT_BODY}'; }}")

        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────
        top = QFrame()
        top.setFixedHeight(60)
        top.setStyleSheet(f"QFrame {{ background: {SIDEBAR_BG}; border-bottom: 1px solid {BORDER}; }}")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(28, 0, 28, 0)

        logo = QLabel("Parker")
        logo.setFont(QFont(FONT_BODY, 15, QFont.Bold))
        logo.setStyleSheet(f"color: {TEXT}; border: none;")
        top_lay.addWidget(logo)

        top_lay.addStretch()

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setFont(QFont(FONT_BODY, 9))
        self.status_lbl.setStyleSheet(f"color: {TEXT_DIM}; border: none; margin-right: 15px;")
        top_lay.addWidget(self.status_lbl)

        # New chat button
        self.new_chat_btn = QPushButton("New Chat ＋")
        self.new_chat_btn.setCursor(Qt.PointingHandCursor)
        self.new_chat_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_DIM}; 
                border: 1px solid {BORDER}; border-radius: 6px; 
                padding: 6px 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {USER_BG}; color: {TEXT}; }}
        """)
        self.new_chat_btn.clicked.connect(self._clear_chat)
        top_lay.addWidget(self.new_chat_btn)

        root.addWidget(top)

        # ── Chat area ────────────────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG}; border: none; }}
            QScrollBar:vertical {{ width: 8px; background: {BG}; border: none; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 40px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::handle:vertical:hover {{ background: #3f3f46; }}
        """)

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet(f"background: {BG}; border: none;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(0, 40, 0, 40)
        self.chat_layout.setSpacing(16)

        center = QHBoxLayout()
        center.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.msg_column = QVBoxLayout()
        self.msg_column.setSpacing(24)
        self.msg_column.addStretch()
        center.addLayout(self.msg_column, 0)
        center.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.chat_layout.addLayout(center)

        self.col_widget = QWidget()
        self.col_widget.setMaximumWidth(780)
        self.col_widget.setMinimumWidth(400)
        self.col_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._msg_layout = QVBoxLayout(self.col_widget)
        self._msg_layout.setContentsMargins(12, 0, 12, 0)
        self._msg_layout.setSpacing(16)
        self._msg_layout.addStretch()

        wrapper = QHBoxLayout()
        wrapper.addStretch()
        wrapper.addWidget(self.col_widget)
        wrapper.addStretch()
        self.chat_layout.addLayout(wrapper)

        self.scroll.setWidget(self.chat_container)
        root.addWidget(self.scroll, 1)

        # ── Input bar ────────────────────────────────────────────
        input_container = QWidget()
        input_container.setStyleSheet(f"background: {BG}; border: none;")
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(20, 10, 20, 24)

        input_frame = QFrame()
        input_frame.setMaximumWidth(780)
        input_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        input_frame.setStyleSheet(f"""
            QFrame {{
                background: {INPUT_BG};
                border: 1px solid {BORDER};
                border-radius: 20px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 0, 0, 80)) 
        input_frame.setGraphicsEffect(shadow)

        bar_lay = QHBoxLayout(input_frame)
        bar_lay.setContentsMargins(18, 4, 8, 4)
        bar_lay.setSpacing(10)
        bar_lay.setAlignment(Qt.AlignBottom)

        self.input = ChatInputEdit()
        self.input.submit.connect(self._submit)
        bar_lay.addWidget(self.input, 1)

        # Bottom-right button container (aligns with bottom regardless of text height)
        btn_lay = QHBoxLayout()
        btn_lay.setContentsMargins(0, 0, 0, 4)
        
        self.voice_btn = QPushButton("🎙")
        self.voice_btn.setFixedSize(38, 38)
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        self.voice_btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {TEXT_DIM}; border: none; border-radius: 19px; font-size: 16px; }} QPushButton:hover {{ background: {BORDER}; color: {TEXT}; }}")
        self.voice_btn.clicked.connect(self._start_voice)
        btn_lay.addWidget(self.voice_btn)

        self.send_btn = QPushButton("↑")
        self.send_btn.setFixedSize(38, 38)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet(f"QPushButton {{ background: {ACCENT}; color: {ACCENT_FG}; border: none; border-radius: 19px; font-size: 20px; font-weight: bold; padding-bottom: 2px; }} QPushButton:hover {{ background: {ACCENT_HOVER}; }} QPushButton:disabled {{ background: {BORDER}; color: {TEXT_DIM}; }}")
        self.send_btn.clicked.connect(lambda: self._submit(self.input.toPlainText().strip()))
        btn_lay.addWidget(self.send_btn)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(38, 38)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setStyleSheet(f"QPushButton {{ background: {BORDER}; color: {TEXT}; border: none; border-radius: 19px; font-size: 14px; font-weight: bold; padding-bottom: 2px; }} QPushButton:hover {{ background: #ef4444; color: white; }}")
        self.stop_btn.clicked.connect(self._stop_generation)
        self.stop_btn.hide()
        btn_lay.addWidget(self.stop_btn)

        bar_lay.addLayout(btn_lay)

        h_wrapper = QHBoxLayout()
        h_wrapper.addStretch()
        h_wrapper.addWidget(input_frame)
        h_wrapper.addStretch()
        input_layout.addLayout(h_wrapper)

        footer = QLabel("Parker can make mistakes. Verify important information.")
        footer.setFont(QFont(FONT_BODY, 8))
        footer.setStyleSheet(f"color: {TEXT_DIM}; border: none; margin-top: 5px;")
        footer.setAlignment(Qt.AlignCenter)
        input_layout.addWidget(footer)

        root.addWidget(input_container)

    # ── Actions ──────────────────────────────────────────────────
    def _clear_chat(self):
        # Clear the UI layout (except the stretch at the bottom)
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.input.clear()
        self.input.setFocus()
        if self._busy:
            self._stop_generation()

        # Rotate thread_id so the checkpointer starts a fresh conversation.
        # Long-term memory (facts, profile, tasks) persists — only chat history resets.
        self.thread_id = str(uuid.uuid4())
        self._set_status("Ready")

    def _submit(self, text: str):
        if not text or self._busy:
            return
        self.input.clear()
        self._last_input = text
        self._busy = True
        self._set_ui_state(generating=True)

        self._add_message("user", text)
        self._ai_msg = self._add_message("parker", "")
        self._set_status("Thinking…")

        config = {
            "configurable": {
                "user_id": self.user_id,
                "thread_id": self.thread_id,
            }
        }
        self.worker = Worker(self.graph, config, text)
        self.worker.token.connect(self._on_token)
        self.worker.status.connect(self._on_status)
        self.worker.finished.connect(self._on_done)
        self.worker.start()

    def _start_voice(self):
        if self._busy: return
        self._busy = True
        self._set_ui_state(generating=True)
        self._set_status("Listening…")

        self.v_worker = VoiceWorker()
        self.v_worker.result.connect(self._on_voice_ok)
        self.v_worker.error.connect(self._on_voice_err)
        self.v_worker.start()

    def _on_voice_ok(self, text: str):
        self._busy = False
        self._submit(text)

    def _on_voice_err(self, err: str):
        self._set_status("Ready")
        self._set_ui_state(generating=False)
        self._busy = False
        self._add_message("parker", f"Voice error: {err}")

    def _stop_generation(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self._set_status("Stopped")
            if self._ai_msg:
                self._ai_msg.append_text(" [Stopped]")
                self._ai_msg.finalize_markdown()
            self._on_done(None)

    def _on_token(self, chunk: str):
        if self._ai_msg:
            self._ai_msg.append_text(chunk)
            self._scroll_bottom()

    def _on_status(self, s: str):
        labels = {"thinking": "Thinking…", "responding": "Writing…", "done": "Ready", "error": "Error"}
        self._set_status(labels.get(s, s))

    def _on_done(self, full_response: str):
        self._busy = False
        self._set_ui_state(generating=False)
        self.input.setFocus()
        
        # Parse final markdown formatting
        if self._ai_msg:
            self._ai_msg.finalize_markdown()

        # The graph already handles memory storage via remember_node.
        # We only need to speak the response.
        if full_response is not None and full_response:
            threading.Thread(target=speak, args=(full_response,), daemon=True).start()

    # ── Helpers ──────────────────────────────────────────────────
    def _add_message(self, role: str, text: str) -> ChatMessage:
        msg = ChatMessage(role, text)
        msg.setMaximumWidth(760)
        idx = self._msg_layout.count() - 1
        self._msg_layout.insertWidget(idx, msg)
        self._scroll_bottom()
        return msg

    def _scroll_bottom(self):
        QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _set_status(self, text: str):
        self.status_lbl.setText(text)

    def _set_ui_state(self, generating: bool):
        # Swap buttons
        if generating:
            self.voice_btn.hide()
            self.send_btn.hide()
            self.stop_btn.show()
        else:
            self.stop_btn.hide()
            self.voice_btn.show()
            self.send_btn.show()
        
        self.input.setReadOnly(generating)


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    app.setStyle("Fusion")

    try:
        store = create_store()
        checkpointer = create_checkpointer()
        
        setup_database(store, checkpointer)

        win = ParkerApp(store, checkpointer)
        win.show()
        sys.exit(app.exec())
    except Exception as e:
        QMessageBox.critical(
            None, 
            "Database Connection Error", 
            f"Could not connect to PostgreSQL.\\n\\nPlease make sure your Docker container is running:\\n\\n`docker compose up -d`\\n\\nError Details:\\n{e}"
        )
        sys.exit(1)