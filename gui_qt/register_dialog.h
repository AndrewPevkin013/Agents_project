#pragma once

#include <QDialog>

#include "auth_client.h"

class QLabel;
class QLineEdit;
class QPushButton;

class RegisterDialog final : public QDialog
{
    Q_OBJECT

public:
    explicit RegisterDialog(
        AuthClient *authClient,
        QWidget *parent = nullptr);

private:
    AuthClient *m_authClient = nullptr;

    QLineEdit *m_username = nullptr;
    QLineEdit *m_email = nullptr;
    QLineEdit *m_password = nullptr;
    QLineEdit *m_passwordRepeat = nullptr;
    QLabel *m_errorLabel = nullptr;
    QPushButton *m_registerButton = nullptr;

    void buildUi();
    void submit();
    void setBusy(bool busy);
};
