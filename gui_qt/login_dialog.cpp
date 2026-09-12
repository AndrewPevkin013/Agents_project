#include "login_dialog.h"

#include <QFormLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>

#include "register_dialog.h"

LoginDialog::LoginDialog(
    AuthClient *authClient,
    QWidget *parent)
    : QDialog(parent)
    , m_authClient(authClient)
{
    setWindowTitle("Sign in");
    setModal(true);
    resize(470, 430);

    buildUi();

    connect(
        m_authClient,
        &AuthClient::loginSucceeded,
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

void LoginDialog::buildUi()
{
    setStyleSheet(R"(
        QDialog {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #FFFFFF,
                stop:0.55 #F5FBFA,
                stop:1 #E9F7F5);
            color: #243434;
        }

        QLabel {
            color: #344947;
        }

        QLabel#title {
            color: #163C3A;
            font-size: 27px;
            font-weight: 700;
        }

        QLabel#subtitle {
            color: #718381;
            font-size: 13px;
        }

        QLabel#error {
            color: #B94D4D;
            background: #FFF0F0;
            border: 1px solid #F0C6C6;
            border-radius: 8px;
            padding: 9px;
        }

        QLineEdit {
            color: #243434;
            background: #FFFFFF;
            border: 1px solid #D2E1DF;
            border-radius: 10px;
            padding: 11px;
            font-size: 14px;
            selection-background-color: #B7EAE6;
        }

        QLineEdit:hover {
            border-color: #B7D7D4;
        }

        QLineEdit:focus {
            border: 1px solid #0ABAB5;
        }

        QPushButton {
            min-height: 40px;
            color: #36504E;
            background: #FFFFFF;
            border: 1px solid #D3E2E0;
            border-radius: 10px;
            padding: 0 16px;
        }

        QPushButton:hover {
            color: #076D69;
            background: #EAF7F5;
            border-color: #A8D9D5;
        }

        QPushButton#primary {
            color: white;
            font-weight: 700;

            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #0ABAB5,
                stop:1 #079A96);

            border: 1px solid #078D89;
        }

        QPushButton#primary:hover {
            background: #079E99;
        }

        QPushButton:disabled {
            color: #9CAAA9;
            background: #EDF2F1;
            border-color: #E0E8E7;
        }
    )");

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(42, 38, 42, 34);
    root->setSpacing(14);

    auto *title = new QLabel("MULTI-AGENT", this);
    title->setObjectName("title");

    auto *subtitle =
        new QLabel("Sign in to your AI workspace", this);
    subtitle->setObjectName("subtitle");

    m_errorLabel = new QLabel(this);
    m_errorLabel->setObjectName("error");
    m_errorLabel->setWordWrap(true);
    m_errorLabel->hide();

    m_authUrl =
        new QLineEdit(m_authClient->baseUrl(), this);
    m_authUrl->setPlaceholderText(
        "http://127.0.0.1:8080");

    m_login = new QLineEdit(this);
    m_login->setPlaceholderText("Username or email");

    m_password = new QLineEdit(this);
    m_password->setPlaceholderText("Password");
    m_password->setEchoMode(QLineEdit::Password);

    m_loginButton = new QPushButton("Sign in", this);
    m_loginButton->setObjectName("primary");

    auto *registerButton =
        new QPushButton("Create account", this);

    root->addWidget(title);
    root->addWidget(subtitle);
    root->addSpacing(8);
    root->addWidget(m_errorLabel);
    root->addWidget(new QLabel("Auth server", this));
    root->addWidget(m_authUrl);
    root->addWidget(new QLabel("Login", this));
    root->addWidget(m_login);
    root->addWidget(new QLabel("Password", this));
    root->addWidget(m_password);
    root->addSpacing(5);
    root->addWidget(m_loginButton);
    root->addWidget(registerButton);

    connect(
        m_loginButton,
        &QPushButton::clicked,
        this,
        &LoginDialog::submitLogin);

    connect(
        registerButton,
        &QPushButton::clicked,
        this,
        &LoginDialog::openRegistration);

    connect(
        m_password,
        &QLineEdit::returnPressed,
        this,
        &LoginDialog::submitLogin);
}

void LoginDialog::submitLogin()
{
    const QString login = m_login->text().trimmed();
    const QString password = m_password->text();

    if (login.isEmpty() || password.isEmpty()) {
        m_errorLabel->setText(
            "Enter login and password.");
        m_errorLabel->show();
        return;
    }

    m_errorLabel->hide();

    m_authClient->setBaseUrl(
        m_authUrl->text().trimmed());

    setBusy(true);
    m_authClient->login(login, password);
}

void LoginDialog::openRegistration()
{
    m_authClient->setBaseUrl(
        m_authUrl->text().trimmed());

    RegisterDialog dialog(m_authClient, this);

    if (dialog.exec() == QDialog::Accepted) {
        accept();
    }
}

void LoginDialog::setBusy(bool busy)
{
    m_loginButton->setEnabled(!busy);
    m_loginButton->setText(
        busy ? "Signing in..." : "Sign in");

    m_login->setEnabled(!busy);
    m_password->setEnabled(!busy);
    m_authUrl->setEnabled(!busy);
}
