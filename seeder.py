from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.custom_gpts_paywall.models import CustomGPTApplication, GPTAppSession, User
import random
from datetime import timedelta

DATABASE_URI = "postgresql://postgres:postgres@postgres:5432/custom_gpts_paywall"
engine = create_engine(DATABASE_URI)
Session = sessionmaker(bind=engine)
session = Session()

faker = Faker()


def create_fake_custom_gpt_application(user_id):
    return CustomGPTApplication(
        gpt_name=faker.catch_phrase()[:30],
        gpt_description=faker.text()[:30],
        gpt_url=faker.url(),
        verification_medium=random.choice(["Email", "Phone", "Google"]),
        token_expiry=timedelta(days=random.randint(1, 30)),
        user_id=user_id,
    )


def create_fake_user_session(gpt_application_id):
    return GPTAppSession(
        gpt_application_id=gpt_application_id,
        email=faker.email(),
        name=faker.name(),
        created_at=faker.date_time(),
    )


def seed_data(n):
    gpt_apps = list()
    user = User(
        name=faker.name(),
        email=faker.email(),
    )
    session.add(user)
    session.commit()
    for _ in range(5):
        gpt_app = create_fake_custom_gpt_application(user.id)
        gpt_apps.append(gpt_app)
        session.add(gpt_app)
        session.commit()

    for _ in range(n):
        user_session = create_fake_user_session(random.choice(gpt_apps).id)
        session.add(user_session)
    session.commit()


seed_data(10000)
