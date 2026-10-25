import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_AMOUNT_MINOR = 1_000_000_000  # ₹1 crore

TransactionType = Literal["expense", "income"]
PaymentMethod = Literal["UPI", "cash", "debit_card", "credit_card", "bank_transfer", "other"]
Source = Literal["manual", "notification", "import"]
Status = Literal["confirmed", "pending_review", "excluded"]

IdStr = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")]
EpochMs = Annotated[int, Field(ge=0, le=4_102_444_800_000)]  # epoch milliseconds, up to year 2100


# --- auth -----------------------------------------------------------------


def normalise_mobile(value: str) -> str:
    """
    Indian mobile numbers in any common format → E.164 (+91XXXXXXXXXX).
    Accepts "98765 43210", "+91-98765-43210", "098765 43210", "919876543210".
    """
    digits = re.sub(r"D", "", value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]d{9}", digits):
        raise ValueError("Enter a valid 10-digit Indian mobile number.")
    return "+91" + digits


class _MobileIn(BaseModel):
    mobile: str = Field(min_length=10, max_length=20)

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        return normalise_mobile(v)


class Credentials(_MobileIn):
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(_MobileIn):
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    mobile: str


class RegisterOut(UserOut):
    # Shown to the user once so they can reset a forgotten password; only its hash is stored.
    recovery_code: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


RecoveryCode = Field(min_length=16, max_length=40)
NewPassword = Field(min_length=8, max_length=128)


class ResetPasswordIn(_MobileIn):
    recovery_code: str = RecoveryCode
    new_password: str = NewPassword


class ResetPasswordOut(TokenOut):
    # The used code is replaced; this new one is shown once.
    recovery_code: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = NewPassword


class ConfirmPasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class RecoveryCodeOut(BaseModel):
    recovery_code: str


# --- transactions ---------------------------------------------------------


class TransactionBase(BaseModel):
    amount_minor_units: int = Field(gt=0, le=MAX_AMOUNT_MINOR)
    currency: Literal["INR"] = "INR"
    transaction_type: TransactionType = "expense"
    category_id: str | None = Field(default=None, max_length=64)
    merchant: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    payment_method: PaymentMethod
    transaction_datetime: EpochMs
    source: Source = "manual"
    source_package: str | None = Field(default=None, max_length=255)
    external_reference: str | None = Field(default=None, max_length=64)
    status: Status = "confirmed"
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_user_confirmed: bool = True


class TransactionCreate(TransactionBase):
    # Optional: phones send their own UUID; the server generates one when omitted.
    id: IdStr | None = None


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor_units: int | None = Field(default=None, gt=0, le=MAX_AMOUNT_MINOR)
    transaction_type: TransactionType | None = None
    category_id: str | None = Field(default=None, max_length=64)
    merchant: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    payment_method: PaymentMethod | None = None
    transaction_datetime: EpochMs | None = None
    status: Status | None = None
    is_user_confirmed: bool | None = None


class TransactionOut(TransactionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: int
    updated_at: int
    deleted_at: int | None = None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


# --- budgets & insights ---------------------------------------------------


class BudgetIn(BaseModel):
    monthly_budget_minor: int | None = Field(default=None, gt=0, le=100 * MAX_AMOUNT_MINOR)


class BudgetOut(BaseModel):
    monthly_budget_minor: int | None
    updated_at: int


class CategoryTotalOut(BaseModel):
    category_id: str | None
    name: str
    total: int
    count: int
    percent: int


class SummaryOut(BaseModel):
    timezone: Literal["Asia/Kolkata"] = "Asia/Kolkata"
    today: int
    week: int
    month: int
    daily_average: int
    days_elapsed: int
    budget: int | None
    budget_remaining: int | None
    previous_month_same_period: int
    change_percent: int | None
    period_label: str


# --- sync -----------------------------------------------------------------


class SyncTransaction(TransactionBase):
    id: IdStr
    created_at: EpochMs
    updated_at: EpochMs
    deleted_at: EpochMs | None = None


class SyncCategory(BaseModel):
    id: IdStr
    name: str = Field(min_length=1, max_length=30)
    icon: str = Field(max_length=64)
    color: str = Field(max_length=16)
    counts_as_spending: bool = True
    is_archived: bool = False
    sort_order: int = 0
    updated_at: EpochMs


class SyncBudget(BaseModel):
    monthly_budget_minor: int | None = Field(default=None, gt=0, le=100 * MAX_AMOUNT_MINOR)
    updated_at: EpochMs


class SyncRequest(BaseModel):
    cursor: int | None = Field(default=None, ge=0)
    transactions: list[SyncTransaction] = []
    categories: list[SyncCategory] = []
    budget: SyncBudget | None = None


class SyncResponse(BaseModel):
    cursor: int
    transactions: list[SyncTransaction]
    categories: list[SyncCategory]
    budget: SyncBudget | None
