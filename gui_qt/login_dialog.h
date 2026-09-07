#pragma once

#include <QDialog>

#include "auth_client.h"

class QLabel;
class QLineEdit;
class QPushButton;

class LoginDialog final : public QDialog
{
    Q_OBJECT

public:
    explicit LoginDialog(
        AuthClient *authClient,
        QWidget *parent = nullptr);

private:
    AuthClient *m_authClient = nullptr;

    QLineEdit *m_authUrl = nullptr;
    QLineEdit *m_login = nullptr;
    QLineEdit *m_password = nullptr;
    QLabel *m_errorLabel = nullptr;
    QPushButton *m_loginButton = nullptr;

    void buildUi();
    void submitLogin();
    void openRegistration();
    void setBusy(bool busy);
};
