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
                stop:0 #09090c,
                stop:0.55 #111015,
                stop:1 #251014);
            color: #eeeeef;
        }

        QLabel#title {
            color: #f4f4f5;
            font-size: 27px;
            font-weight: 700;
        }

        QLabel#subtitle {
            color: #8f8f98;
            font-size: 13px;
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
            min-height: 40px;
            color: #ececef;
            background: #24242b;
            border: 1px solid #3c3c44;
            border-radius: 10px;
            padding: 0 16px;
        }

        QPushButton:hover {
            background: #342126;
            border-color: #793039;
        }

        QPushButton#primary {
            color: white;
            font-weight: 700;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 #821d27,
                stop:1 #bd3944);
            border: 1px solid #ce4a55;
        }

        QPushButton#primary:hover {
            background: #a42b36;
        }

        QPushButton:disabled {
            color: #77777e;
            background: #222228;
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
