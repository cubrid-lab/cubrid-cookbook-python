"""AI chatbot backend — FastAPI server with CUBRID state persistence.

A production-shaped AI chatbot that stores conversation history,
user profiles, and message analytics in CUBRID. Demonstrates:
- SQLAlchemy ORM with JSON columns for LLM I/O
- FastAPI for the API layer
- CUBRID as the conversation memory store
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


class ChatUser(Base):
    __tablename__ = "chat_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=sa.text("SYS_DATETIME"))

    conversations: Mapped[list["ChatConversation"]] = relationship(back_populates="user")


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("chat_users.id"))
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=sa.text("SYS_DATETIME"))

    user: Mapped["ChatUser"] = relationship(back_populates="conversations")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        order_by="ChatMessage.id",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("chat_conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # user / assistant / system / tool
    content: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=sa.text("SYS_DATETIME"))

    conversation: Mapped["ChatConversation"] = relationship(back_populates="messages")


def simulate_llm_response(user_message: str) -> str:
    """Simulate an LLM response — replace with OpenAI/Anthropic API call."""
    return f"I understand you said: '{user_message}'. How can I help you with that?"


def main() -> None:
    engine = sa.create_engine(DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Create a user with AI preferences stored as JSON
        user = ChatUser(
            username="alice",
            display_name="Alice Kim",
            preferences={"model": "gpt-4", "temperature": 0.7, "max_tokens": 2000},
        )
        session.add(user)
        session.flush()
        print(f"User created: {user.id} ({user.username})")

        # Create a conversation
        conv = ChatConversation(user_id=user.id, title="CUBRID + AI Demo")
        session.add(conv)
        session.flush()
        print(f"Conversation: {conv.id}")

        # Simulate a chat exchange
        exchanges = [
            ("user", "Hello! Can you help me analyze my data?"),
            ("assistant", "Of course! I'd be happy to help you analyze your CUBRID data."),
            ("user", "What tables do I have?"),
            ("assistant", "You have tables for users, products, and orders."),
        ]

        for role, content in exchanges:
            msg = ChatMessage(
                conversation_id=conv.id,
                role=role,
                content=content,
                metadata_={"turn": len(conv.messages), "source": "demo"},
                token_count=len(content.split()),
            )
            session.add(msg)

        session.commit()

        # Query conversation history with JSON metadata
        msgs = (
            session.execute(
                sa.select(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
                .order_by(ChatMessage.id)
            )
            .scalars()
            .all()
        )

        print(f"\nConversation transcript ({len(msgs)} messages):")
        for m in msgs:
            print(f"  [{m.role}] {m.content[:60]} (tokens: {m.token_count})")

        # Verify JSON metadata round-trip
        assert msgs[0].metadata_["turn"] == 0
        assert msgs[0].metadata_["source"] == "demo"
        print(f"\n  JSON metadata round-trip: ✓")

        # User preferences (JSON column)
        print(f"  User preferences: {user.preferences}")
        assert user.preferences["model"] == "gpt-4"

    engine.dispose()
    print("\n✓ AI chatbot backend working")


if __name__ == "__main__":
    main()
