from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_AMOUNT_MINOR = 1_000_000_000  # ₹1 crore

TransactionType = Literal["expense", "income"]
PaymentMethod = Literal["UPI", "cash", "debit_card", "credit_card", "bank_transfer", "other"]
Source = Literal["manual", "notification", "import"]
Status = Literal["confirmed", "pending_review", "excluded"]

IdStr = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")]
EpochMs = Annotated[int, Field(ge=0, le=4_102_444_800_000)]  # epoch milliseconds, up to year 2100


# --- auth -----------------------------------------------------------------


class GoogleSignInIn(BaseModel):
    # The ID token from Google Sign-In on the phone (a signed JWT, verified server-side).
    id_token: str = Field(min_length=20, max_length=4096)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str | None
    name: str | None


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class SignInOut(TokenOut):
    user: UserOut
    # True when this sign-in created the account.
    created: bool


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


BudgetAmount = Field(default=None, gt=0, le=100 * MAX_AMOUNT_MINOR)
DayKey = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class BudgetIn(BaseModel):
    monthly_budget_minor: int | None = BudgetAmount
    daily_budget_minor: int | None = BudgetAmount


class BudgetOut(BaseModel):
    monthly_budget_minor: int | None
    daily_budget_minor: int | None
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
    budget_minor: int | None = Field(default=None, gt=0, le=100 * MAX_AMOUNT_MINOR)
    updated_at: EpochMs


class SyncBudget(BaseModel):
    monthly_budget_minor: int | None = BudgetAmount
    daily_budget_minor: int | None = BudgetAmount
    updated_at: EpochMs


class SyncDayBudget(BaseModel):
    day_key: DayKey
    # null = the day's override was removed (falls back to the usual daily budget)
    amount_minor: int | None = BudgetAmount
    updated_at: EpochMs


class SyncOverrun(BaseModel):
    scope: Literal["day", "month"]
    period_key: str = Field(pattern=r"^\d{4}-\d{2}(-\d{2})?$")
    budget_minor: int = Field(ge=0, le=100 * MAX_AMOUNT_MINOR)
    spent_minor: int = Field(ge=0, le=100 * MAX_AMOUNT_MINOR)
    reason_code: str = Field(min_length=1, max_length=32, pattern=r"^[a-z_]+$")
    note: str | None = Field(default=None, max_length=300)
    created_at: EpochMs
    updated_at: EpochMs

    @model_validator(mode="after")
    def _key_matches_scope(self) -> "SyncOverrun":
        if (len(self.period_key) == 10) != (self.scope == "day"):
            raise ValueError("period_key must be YYYY-MM-DD for a day and YYYY-MM for a month.")
        return self


MonthKey = Annotated[str, Field(pattern=r"^\d{4}-\d{2}$")]


class SyncReminder(BaseModel):
    id: IdStr
    kind: Literal["emi", "bill"]
    name: str = Field(min_length=1, max_length=60)
    amount_minor: int = Field(gt=0, le=100 * MAX_AMOUNT_MINOR)
    due_day: int = Field(ge=1, le=31)
    category_id: str | None = Field(default=None, max_length=64)
    start_month: MonthKey
    total_months: int | None = Field(default=None, ge=1, le=480)
    remind_days_before: int = Field(default=1, ge=0, le=7)
    times_per_day: int = Field(default=1, ge=1, le=3)
    remind_times: str = Field(default="", max_length=32, pattern=r"^(\d{1,4}(,\d{1,4}){0,2})?$")
    snooze: Literal["15m", "1h", "3h", "tomorrow"] = "1h"
    created_at: EpochMs
    updated_at: EpochMs
    deleted_at: EpochMs | None = None


class SyncReminderPayment(BaseModel):
    reminder_id: IdStr
    period_key: MonthKey
    transaction_id: IdStr | None = None
    created_expense: bool = False
    counted: bool = True
    paid_at: EpochMs
    updated_at: EpochMs
    deleted_at: EpochMs | None = None


class SyncSplit(BaseModel):
    id: IdStr
    transaction_id: IdStr
    person: str = Field(min_length=1, max_length=40)
    amount_minor: int = Field(gt=0, le=MAX_AMOUNT_MINOR)
    settled_at: EpochMs | None = None
    created_at: EpochMs
    updated_at: EpochMs
    deleted_at: EpochMs | None = None


class SyncRequest(BaseModel):
    cursor: int | None = Field(default=None, ge=0)
    transactions: list[SyncTransaction] = []
    categories: list[SyncCategory] = []
    budget: SyncBudget | None = None
    day_budgets: list[SyncDayBudget] = []
    overruns: list[SyncOverrun] = []
    reminders: list[SyncReminder] = []
    reminder_payments: list[SyncReminderPayment] = []
    splits: list[SyncSplit] = []


class SyncResponse(BaseModel):
    cursor: int
    transactions: list[SyncTransaction]
    categories: list[SyncCategory]
    budget: SyncBudget | None
    day_budgets: list[SyncDayBudget] = []
    overruns: list[SyncOverrun] = []
    reminders: list[SyncReminder] = []
    reminder_payments: list[SyncReminderPayment] = []
    splits: list[SyncSplit] = []
