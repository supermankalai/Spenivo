from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MAX_AMOUNT_MINOR = 1_000_000_000  # ₹1 crore

TransactionType = Literal["expense", "income"]
PaymentMethod = Literal["UPI", "cash", "debit_card", "credit_card", "bank_transfer", "other"]
Source = Literal["manual", "notification", "import"]
Status = Literal["confirmed", "pending_review", "excluded"]

IdStr = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")]
EpochMs = Annotated[int, Field(ge=0, le=4_102_444_800_000)]  # epoch milliseconds, up to year 2100


# --- auth -----------------------------------------------------------------


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


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
