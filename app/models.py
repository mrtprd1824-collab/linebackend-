from .extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone

# กำหนด Timezone ไว้ที่ส่วนกลาง
BANGKOK_TZ = timezone(timedelta(hours=7))

# --- User Loader (สำหรับ Flask-Login) ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Association Table (สำหรับ Many-to-Many Relationship) ---
oa_group_association = db.Table('oa_group_association',
    db.Column('line_account_id', db.Integer, db.ForeignKey('line_account.id', ondelete="CASCADE"), primary_key=True),
    db.Column('oa_group_id', db.Integer, db.ForeignKey('oa_group.id', ondelete="CASCADE"), primary_key=True)
)

# --- Models ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False) # unique=True สร้าง index ให้อยู่แล้ว
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False, index=True) # <-- [เพิ่ม] เผื่อมีการกรอง user ตาม role
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class OAGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) # unique=True สร้าง index ให้อยู่แล้ว
    
    line_oas = db.relationship('LineAccount', secondary=oa_group_association, back_populates='groups')

    def __repr__(self):
        return f'<OAGroup {self.name}>'

class LineAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    channel_id = db.Column(db.String(100), unique=True, nullable=False) # unique=True สร้าง index ให้อยู่แล้ว
    channel_secret = db.Column(db.String(255), nullable=False)
    channel_access_token = db.Column(db.String(255), nullable=False)
    webhook_path = db.Column(db.String(50), unique=True, nullable=False) # unique=True สร้าง index ให้อยู่แล้ว
    groups = db.relationship('OAGroup', secondary=oa_group_association, back_populates='line_oas')
    messages = db.relationship('LineMessage', back_populates='line_account', cascade="all, delete-orphan")
    users = db.relationship('LineUser', back_populates='line_account', cascade="all, delete-orphan")
    quick_replies = db.relationship('QuickReply', back_populates='line_account', cascade="all, delete-orphan")
    def __repr__(self):
        return f"<LineAccount {self.name}>"

class LineUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), nullable=False)
    
    line_account_id = db.Column(db.Integer, db.ForeignKey('line_account.id', ondelete='CASCADE'), nullable=False, index=True) # <-- [เพิ่ม] Foreign Key ควรมี index เสมอ
    line_account = db.relationship('LineAccount', back_populates='users')

    display_name = db.Column(db.String(255))
    picture_url = db.Column(db.String(1024))
    
    # ข้อมูลลูกค้า
    nickname = db.Column(db.String(100))
    phone = db.Column(db.String(50), index=True) # <-- [เพิ่ม] เพื่อให้ค้นหาลูกค้าจากเบอร์โทรได้เร็ว
    note = db.Column(db.Text)
    
    # สถานะแชท
    status = db.Column(db.String(50), nullable=False, default='read', index=True) # อันนี้ทำไว้ดีแล้ว
    unread_count = db.Column(db.Integer, nullable=False, default=0)
    last_read_timestamp = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True) # <-- [เพิ่ม] สำหรับเรียงลำดับ user ใหม่
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True) # <-- [เพิ่ม] สำหรับเรียงลำดับ user ที่ active

    __table_args__ = (db.UniqueConstraint('line_account_id', 'user_id', name='_line_account_user_uc'),)

    def __repr__(self):
        return f'<LineUser {self.display_name or self.user_id}>'

class LineMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(255), nullable=False) # ไม่ต้องใส่ index เดี่ยวๆ เพราะมี composite index ด้านล่างแล้ว
    line_account_id = db.Column(db.Integer, db.ForeignKey('line_account.id', ondelete='CASCADE'), nullable=False, index=True) # <-- [เพิ่ม] สำคัญมาก! Query ข้อความแทบทุกครั้งต้องผ่าน key นี้
    line_account = db.relationship("LineAccount", back_populates="messages")
    admin_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True) # <-- [เพิ่ม] สำหรับค้นหาข้อความที่แอดมินส่ง
    admin = db.relationship('User')
    message_type = db.Column(db.String(50), nullable=False, default="text", index=True) # <-- [เพิ่ม] เผื่อมีการกรองข้อความตามประเภท
    message_text = db.Column(db.Text)
    message_url = db.Column(db.String(255))
    media_key = db.Column(db.String(512), index=True, nullable=True)
    sticker_id = db.Column(db.String(50))
    package_id = db.Column(db.String(50))
    is_outgoing = db.Column(db.Boolean, default=False, index=True) # <-- [เพิ่ม] สำหรับกรองข้อความเข้า-ออก
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(BANGKOK_TZ), index=True) # <-- [เพิ่ม] สำคัญมาก! สำหรับเรียงลำดับข้อความ
    __table_args__ = (db.Index("ix_line_message_user_time", "user_id", "timestamp"),)

    def __repr__(self):
        return f"<LineMessage {self.user_id}: {self.message_text}>"

class QuickReply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shortcut = db.Column(db.String(50), nullable=False, index=True) # <-- [เพิ่ม] เพื่อให้ค้นหา shortcut ได้เร็ว
    message = db.Column(db.Text, nullable=False)
    
    line_account_id = db.Column(db.Integer, db.ForeignKey('line_account.id', ondelete='CASCADE'), nullable=True, index=True) # <-- [เพิ่ม] สำหรับค้นหา Quick Reply ของ OA นั้นๆ
    line_account = db.relationship('LineAccount', back_populates='quick_replies')

    def __repr__(self):
        return f'<QuickReply {self.shortcut}>'

class Sticker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    packageId = db.Column(db.String(50), nullable=False)
    stickerId = db.Column(db.String(50), nullable=False)

    # <-- [เพิ่ม] Composite Index สำหรับการค้นหาสติกเกอร์
    __table_args__ = (db.Index('ix_package_sticker', 'packageId', 'stickerId'),)

    def __repr__(self):
        return f"Sticker('{self.packageId}', '{self.stickerId}')"