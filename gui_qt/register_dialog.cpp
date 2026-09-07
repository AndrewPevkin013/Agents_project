#include "register_dialog.h"

#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>

RegisterDialog::RegisterDialog(
    AuthClient *authClient,
    QWidget *parent)
    : QDialog(parent)
    , m_authClient(authClient)
{
    setWindowTitle("Create account");
    setModal(true);
    resize(470, 520);

    buildUi();

    connect(
        m_authClient,
        &AuthClient::registrationSucceeded,
        this,
        [this](const QString &, const QString &, const QString &) {
            setBusy(false);
            accept();
        });

    connect(
        m_authClient,
        &AuthClient::authError,
        this,
        [this](const QString &message) {
            setBusy(false);
            m_errorLabel->setText(message);
            m_errorLabel->show();
        });
}

void RegisterDialog::buildUi()
{
    setStyleSheet(R"(
        QDialog {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #09090c,
                stop:0.55 #111015,
                stop:1 #251014);
            color: #eeeeef;
        }

        QLabel#title {
            color: #f4f4f5;
            font-size: 25px;
            font-weight: 700;
        }

        QLabel#subtitle {
            color: #8f8f98;
        }

        QLabel#error {
            color: #ef747d;
            background: #351419;
            border: 1px solid #812832;
            border-radius: 8px;
            padding: 9px;
        }

        QLineEdit {
            color: #f1f1f3;
            background: #19191f;
            border: 1px solid #39343a;
            border-radius: 10px;
            padding: 11px;
            font-size: 14px;
        }

        QLineEdit:focus {
            border: 1px solid #a8323d;
        }

        QPushButton {
            min-height: 42px;
            color: white;
            font-weight: 700;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #821d27,
                stop:1 #bd3944);
            border: 1px solid #ce4a55;
            border-radius: 10px;
        }

        QPushButton:hover {
            background: #a42b36;
        }

        QPushButton:disabled {
            color: #77777e;
            background: #222228;
        }
    )");

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(42, 36, 42, 34);
    root->setSpacing(11);

    auto *title = new QLabel("Create account", this);
    title->setObjectName("title");

    auto *subtitle =
        new QLabel("Your account will be stored in PostgreSQL.", this);
    subtitle->setObjectName("subtitle");

    m_errorLabel = new QLabel(this);
    m_errorLabel->setObjectName("error");
    m_errorLabel->setWordWrap(true);
    m_errorLabel->hide();

    m_username = new QLineEdit(this);
    m_username->setPlaceholderText("andrew");

    m_email = new QLineEdit(this);
    m_email->setPlaceholderText("andrew@example.com");

    m_password = new QLineEdit(this);
    m_password->setPlaceholderText(
        "At least 10 characters");
    m_password->setEchoMode(QLineEdit::Password);

    m_passwordRepeat = new QLineEdit(this);
    m_passwordRepeat->setPlaceholderText(
        "Repeat password");
    m_passwordRepeat->setEchoMode(QLineEdit::Password);

    m_registerButton =
        new QPushButton("Create account", this);

    root->addWidget(title);
    root->addWidget(subtitle);
    root->addSpacing(5);
    root->addWidget(m_errorLabel);
    root->addWidget(new QLabel("Username", this));
    root->addWidget(m_username);
    root->addWidget(new QLabel("Email", this));
    root->addWidget(m_email);
    root->addWidget(new QLabel("Password", this));
    root->addWidget(m_password);
    root->addWidget(new QLabel("Repeat password", this));
    root->addWidget(m_passwordRepeat);
    root->addSpacing(7);
    root->addWidget(m_registerButton);

    connect(
        m_registerButton,
        &QPushButton::clicked,
        this,
        &RegisterDialog::submit);

    connect(
        m_passwordRepeat,
        &QLineEdit::returnPressed,
        this,
        &RegisterDialog::submit);
}

void RegisterDialog::submit()
{
    const QString username =
        m_username->text().trimmed();
    const QString email =
        m_email->text().trimmed();
    const QString password =
        m_password->text();
    const QString repeat =
        m_passwordRepeat->text();

    if (username.isEmpty()
        || email.isEmpty()
        || password.isEmpty()) {
        m_errorLabel->setText(
            "Fill in all fields.");
        m_errorLabel->show();
        return;
    }

    if (password != repeat) {
        m_errorLabel->setText(
            "Passwords do not match.");
        m_errorLabel->show();
        return;
    }

    if (password.size() < 10) {
        m_errorLabel->setText(
            "Password must contain at least 10 characters.");
        m_errorLabel->show();
        return;
    }

    m_errorLabel->hide();
    setBusy(true);

    m_authClient->registerUser(
        username,
        email,
        password);
}

void RegisterDialog::setBusy(bool busy)
{
    m_registerButton->setEnabled(!busy);
    m_registerButton->setText(
        busy ? "Creating..." : "Create account");

    m_username->setEnabled(!busy);
    m_email->setEnabled(!busy);
    m_password->setEnabled(!busy);
    m_passwordRepeat->setEnabled(!busy);
}
