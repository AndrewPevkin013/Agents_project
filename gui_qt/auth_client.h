#pragma once

#include <QObject>
#include <QJsonObject>
#include <QNetworkAccessManager>

class AuthClient final : public QObject
{
    Q_OBJECT

public:
    explicit AuthClient(QObject *parent = nullptr);

    void setBaseUrl(const QString &url);
    [[nodiscard]] QString baseUrl() const;

    void registerUser(
        const QString &username,
        const QString &email,
        const QString &password);

    void login(
        const QString &login,
        const QString &password);

    void refresh();
    void logout();
    void getCurrentUser();

    [[nodiscard]] QString accessToken() const;
    [[nodiscard]] QString refreshToken() const;
    [[nodiscard]] QString username() const;
    [[nodiscard]] bool isAuthenticated() const;

signals:
    void loginSucceeded(
        const QString &username,
        const QString &accessToken,
        const QString &refreshToken);

    void registrationSucceeded(
        const QString &username,
        const QString &accessToken,
        const QString &refreshToken);

    void logoutSucceeded();
    void currentUserReady(const QJsonObject &user);
    void authError(const QString &message);

private:
    QString m_baseUrl = "http://127.0.0.1:8080";
    QString m_accessToken;
    QString m_refreshToken;
    QString m_username;
    QNetworkAccessManager m_network;

    void postJson(
        const QString &path,
        const QJsonObject &body,
        const QString &operation);

    void parseTokenResponse(
        const QByteArray &data,
        const QString &operation);
};
