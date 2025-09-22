import click
from app import create_app
from app.extensions import db
from app.models import User

app = create_app()

# เพิ่มบรรทัดนี้เพื่อดีบัก
print(f"DEBUG: manage.py is using database -> {app.config.get('SQLALCHEMY_DATABASE_URI')}")

@app.shell_context_processor
def ctx():
    return {"db": db, "User": User}

@app.cli.command("create-admin")
@click.option("--email", required=True)
@click.option("--password", required=True)
def create_admin(email, password):
    print("--- Running create_admin function ---")
    with app.app_context():
        print("--- Entered app context ---")

        existing_user = User.query.filter_by(email=email).first()
        print(f"--- Found existing user: {existing_user} ---")

        if existing_user:
            click.echo("Admin already exists")
            return

        print("--- Creating new user object ---")
        u = User(email=email)
        u.set_password(password)

        print("--- Adding user to session ---")
        db.session.add(u)

        print("--- Committing to database ---")
        db.session.commit()

        print("--- Commit finished ---")
        click.echo("Admin created")