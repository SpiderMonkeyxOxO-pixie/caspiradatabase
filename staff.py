"""The named support team who sign in and answer the (AI) customers.

Each person gets their own sign-in account ("CSPR-<name>") and their own chat identity
("庞统 (Customer Service)"), so two people with the same position never look alike in a
conversation. `view` decides which existing console view they land on — change it here if a
person should see a different one (valid values: the role names in views.ROLE_VIEW).
"""

STAFF = [
    {
        "name": "庞统", "position": "Customer Service", "view": "Customer Service", "color": "#f472b6",
        "details": "Helps users with account access issues, such as password reset or login problems. "
                   "Guides them on how to use the platform.",
    },
    {
        "name": "马超", "position": "Manager", "view": "General Manager", "color": "#fb923c",
        "details": "Supervises Customer Service operations, monitors team performance, handles escalations "
                   "and ensures high-quality customer support according to company standards.",
    },
    {
        "name": "典韦", "position": "Customer Service", "view": "Customer Service", "color": "#e879f9",
        "details": "Helps users with account access issues, such as password reset or login problems. "
                   "Guides them on how to use the platform.",
    },
    {
        "name": "Kevin", "position": "Computer Operator", "view": "I.T Assistant", "color": "#38bdf8",
        "details": "Performs tasks using Microsoft Office applications, prepares required documents to enter "
                   "data into computer systems, and monitors and manages email correspondence.",
    },
    {
        "name": "Marcus", "position": "Supervisor", "view": "General Manager", "color": "#a3e635",
        "details": "Supervises Customer Service operations, monitors team performance, handles escalations "
                   "and ensures high-quality customer support according to company standards.",
    },
    {
        "name": "赵云", "position": "I.T Assistant", "view": "I.T Assistant", "color": "#4ade80",
        "details": "Monitors and ensures that IT systems, processes and operations comply with company "
                   "policies, security standards and regulatory requirements.",
    },
    {
        "name": "Chris", "position": "Social Media Support Specialist", "view": "Customer Service",
        "color": "#fbbf24",
        "details": "Assists customers through social media platforms, manages online interactions, resolves "
                   "customer concerns and maintains positive brand communication and engagement.",
    },
]


def identity(person: dict) -> str:
    """Name shown on this person's chat messages, e.g. "庞统 (Customer Service)"."""
    return f"{person['name']} ({person['position']})"


def account(person: dict) -> str:
    """Sign-in account name, in the same style as the role accounts (CSPR-...)."""
    return f"CSPR-{person['name']}"


IDENTITIES = [identity(p) for p in STAFF]
_BY_ACCOUNT = {account(p): p for p in STAFF}
_BY_IDENTITY = {identity(p): p for p in STAFF}


def by_account(account_name: str):
    """The staff member who owns this sign-in account, or None for the original role accounts."""
    return _BY_ACCOUNT.get(account_name)


def by_identity(identity_name: str):
    """The staff member behind this chat identity, or None."""
    return _BY_IDENTITY.get(identity_name)
