"""Covenant taxonomy: every clause in a loan document is mapped to one topic, so different lenders' wording can be
monitored the same way. Keywords power the rule-based baseline classifier."""

TOPICS = {
    # financial covenants: tested against the borrower's numbers
    "FIN_DEBT_EQUITY": ("financial", "Maximum debt-to-equity ratio", ["debt-to-equity", "debt to equity", "d/e", "gearing"]),
    "FIN_SECURITY_COVER": ("financial", "Minimum security / asset cover on the facility", ["security coverage", "security cover", "asset cover"]),
    "FIN_FACR": ("financial", "Minimum fixed asset coverage ratio", ["facr", "fixed asset coverage"]),
    "FIN_INTEREST_COVER": ("financial", "Minimum interest or debt-service coverage (ICR / DSCR)", ["dscr", "interest coverage", "debt service coverage"]),
    # reporting covenants: something must be submitted or done by a date
    "REP_STOCK_STATEMENT": ("reporting", "Periodic stock and book-debt statements", ["stock statement", "book debt statement", "stock and book debt"]),
    "REP_CA_CERTIFICATE": ("reporting", "Periodic chartered-accountant certificate", ["ca certificate", "chartered accountant certificate"]),
    "REP_CHARGE_FILING": ("reporting", "Register the lender's charge with the ROC within a deadline", ["filed with roc", "charge filing", "roc within"]),
    "REP_PARI_PASSU_LETTER": ("reporting", "Obtain pari-passu letter from existing lenders", ["pari-passu letter", "pari passu letter"]),
    "REP_SECURITY_PERFECTION": ("reporting", "Create / perfect security or mortgage within a deadline", ["security creation", "perfection", "equitable mortgage", "cersai"]),
    # consent covenants: the borrower needs the lender's prior consent (or must inform it) before acting
    "CON_FRESH_BORROWING": ("consent", "New borrowing from other lenders", ["fresh loan", "additional limit", "new loan", "availed", "borrowing from", "credit line", "working capital line", "facility from", "noc"]),
    "CON_CHANGE_CONTROL_MGMT": ("consent", "Change in control, ownership, management or board / KMP", ["change in management", "change of control", "resigned", "appointed", "ceo", "cfo", "managing director", "board composition", "key managerial"]),
    "CON_PROMOTER_DILUTION": ("consent", "Dilution or sale of promoter shareholding", ["promoter stake", "promoter sold", "promoter holding", "pledge", "promoter dilution", "stake sale"]),
    "CON_MERGER": ("consent", "Merger, demerger, amalgamation or restructuring scheme", ["merger", "amalgamation", "demerger", "scheme of arrangement"]),
    "CON_INVESTMENTS": ("consent", "Investments or loans in subsidiaries / other entities", ["invested", "investment in", "acquired", "subsidiary", "equity infusion", "inter-corporate loan"]),
    "CON_DIVIDEND": ("consent", "Declaring dividends or distributions", ["dividend", "distribution to shareholders", "buyback"]),
    "CON_CAPITAL_STRUCTURE": ("consent", "Change in capital structure or shareholding pattern", ["capital structure", "share capital", "rights issue", "preferential allotment", "bonus issue"]),
    "CON_CONSTITUTIONAL_DOCS": ("consent", "Amending memorandum or articles of association", ["articles of association", "memorandum of association", "moa", "aoa"]),
    "CON_ENCUMBRANCE": ("consent", "Creating a charge or lien on assets for someone else", ["charge in favour", "lien", "encumbrance", "mortgaged", "hypothecated to"]),
    "CON_ASSET_DISPOSAL": ("consent", "Selling or disposing of assets outside ordinary course", ["sold its", "sale of plant", "disposed", "asset sale", "sale-and-leaseback"]),
    "CON_BUSINESS_CHANGE": ("consent", "Change in the nature of business", ["new line of business", "change in business", "diversif", "exit the business"]),
    "CON_FUND_DIVERSION_END_USE": ("consent", "Using loan money for other purposes or diverting to group companies", ["diverted", "end use", "group company", "associate concern"]),
    "CON_PROMOTER_LOAN_REPAYMENT": ("consent", "Repaying unsecured loans from promoters", ["repaid promoter", "unsecured loan from promoter", "promoter loan"]),
    "CON_PREPAYMENT": ("consent", "Prepaying the loan without lender approval", ["prepaid", "prepayment", "foreclosed the loan"]),
    "CON_ASSIGNMENT": ("consent", "Assigning or transferring rights under the facility", ["assigned", "novation", "transfer of rights"]),
    # events of default: lender may recall the loan
    "EOD_PAYMENT_DEFAULT": ("default", "Missed or delayed payment of principal or interest", ["missed payment", "delayed payment", "overdue", "default in repayment", "emi bounced"]),
    "EOD_RATING_DOWNGRADE": ("default", "Credit rating downgrade", ["downgrade", "rating revised", "rating cut", "watch with negative"]),
    "EOD_SMA_NPA": ("default", "Account classified SMA / NPA by any lender", ["sma-", "sma ", "npa", "special mention account"]),
    "EOD_CROSS_DEFAULT": ("default", "Default or recall under another lender's facility", ["cross default", "recalled by", "another lender declared"]),
    "EOD_INSOLVENCY": ("default", "Insolvency, winding-up or recovery proceedings", ["insolvency", "nclt", "winding up", "ibc", "recovery suit"]),
    "EOD_COVENANT_BREACH": ("default", "Breach of covenants or misleading representations", ["breach of covenant", "misrepresentation", "incorrect representation"]),
    "EOD_MAE": ("default", "Material adverse effect / cessation of business / regulatory action", ["material adverse", "licence suspended", "plant shut", "cessation of business", "fire at"]),
    "EOD_FINANCIAL_RATIOS": ("default", "Financial ratios beyond limits in the loan agreement", ["financial ratios beyond"]),
}
NONE = "NONE"


def category(topic: str) -> str | None:
    return TOPICS[topic][0] if topic in TOPICS else None
