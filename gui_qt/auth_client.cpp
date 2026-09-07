#include "auth_client.h"

#include <QJsonDocument>
#include <QJsonParseError>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrl>

AuthClient::AuthClient(QObject *parent)
    : QObject(parent)
{
}

void AuthClient::setBaseUrl(const QString &url)
{
    m_baseUrl = url.trimmed();
    while (m_baseUrl.endsWith('/')) {
        m_baseUrl.chop(1);
    }
}

QString AuthClient::baseUrl() const
{
    return m_baseUrl;
}

QString AuthClient::accessToken() const
{
    return m_accessToken;
}

QString AuthClient::refreshToken() const
{
    return m_refreshToken;
}

QString AuthClient::username() const
{
    return m_username;
}

bool AuthClient::isAuthenticated() const
{
    return !m_accessToken.isEmpty();
}

void AuthClient::registerUser(
    const QString &username,
    const QString &email,
    const QString &password)
{
    postJson(
        "/auth/register",
        {
            {"username", username.trimmed()},
            {"email", email.trimmed()},
            {"password", password}
        },
        "register");
}

void AuthClient::login(
    const QString &login,
    const QString &password)
{
    postJson(
        "/auth/login",
        {
            {"login", login.trimmed()},
            {"password", password}
        },
        "login");
}

void AuthClient::refresh()
{
    if (m_refreshToken.isEmpty()) {
        emit authError("Refresh token is empty.");
        return;
    }

    postJson(
        "/auth/refresh",
        {{"refresh_token", m_refreshToken}},
        "refresh");
}

void AuthClient::logout()
{
    if (m_refreshToken.isEmpty()) {
        m_accessToken.clear();
        m_refreshToken.clear();
        m_username.clear();
        emit logoutSucceeded();
        return;
    }

    QNetworkRequest request(QUrl(m_baseUrl + "/auth/logout"));
    request.setHeader(
        QNetworkRequest::ContentTypeHeader,
        "application/json");

    const QByteArray payload = QJsonDocument(
        QJsonObject{
            {"refresh_token", m_refreshToken}
        }).toJson(QJsonDocument::Compact);

    QNetworkReply *reply = m_network.post(request, payload);

    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        const QByteArray data = reply->readAll();

        if (reply->error() != QNetworkReply::NoError
            && reply->attribute(
                QNetworkRequest::HttpStatusCodeAttribute).toInt() != 204) {
            emit authError(
                reply->errorString() + "\n"
                + QString::fromUtf8(data));
            reply->deleteLater();
            return;
        }

        m_accessToken.clear();
        m_refreshToken.clear();
        m_username.clear();

        emit logoutSucceeded();
        reply->deleteLater();
    });
}

void AuthClient::getCurrentUser()
{
    if (m_accessToken.isEmpty()) {
        emit authError("Access token is empty.");
        return;
    }

    QNetworkRequest request(QUrl(m_baseUrl + "/auth/me"));
    request.setRawHeader(
        "Authorization",
        ("Bearer " + m_accessToken).toUtf8());

    QNetworkReply *reply = m_network.get(request);

    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        const QByteArray data = reply->readAll();

        if (reply->error() != QNetworkReply::NoError) {
            emit authError(
                reply->errorString() + "\n"
                + QString::fromUtf8(data));
            reply->deleteLater();
            return;
        }

        QJsonParseError error;
        const QJsonDocument document =
            QJsonDocument::fromJson(data, &error);

        if (error.error != QJsonParseError::NoError
            || !document.isObject()) {
            emit authError("Invalid /auth/me response.");
            reply->deleteLater();
            return;
        }

        emit currentUserReady(document.object());
        reply->deleteLater();
    });
}

void AuthClient::postJson(
    const QString &path,
    const QJsonObject &body,
    const QString &operation)
{
    QNetworkRequest request(QUrl(m_baseUrl + path));
    request.setHeader(
        QNetworkRequest::ContentTypeHeader,
        "application/json");

    QNetworkReply *reply = m_network.post(
        request,
        QJsonDocument(body).toJson(QJsonDocument::Compact));

    connect(reply, &QNetworkReply::finished,
            this, [this, reply, operation]() {
        const QByteArray data = reply->readAll();

        if (reply->error() != QNetworkReply::NoError) {
            QString detail = QString::fromUtf8(data);

            QJsonParseError parseError;
            const QJsonDocument document =
                QJsonDocument::fromJson(data, &parseError);

            if (parseError.error == QJsonParseError::NoError
                && document.isObject()) {
                detail =
                    document.object().value("detail").toString(detail);
            }

            emit authError(detail);
            reply->deleteLater();
            return;
        }

        parseTokenResponse(data, operation);
        reply->deleteLater();
    });
}

void AuthClient::parseTokenResponse(
    const QByteArray &data,
    const QString &operation)
{
    QJsonParseError error;
    const QJsonDocument document =
        QJsonDocument::fromJson(data, &error);

    if (error.error != QJsonParseError::NoError
        || !document.isObject()) {
        emit authError("Auth service returned invalid JSON.");
        return;
    }

    const QJsonObject root = document.object();
    const QJsonObject user = root.value("user").toObject();

    m_accessToken = root.value("access_token").toString();
    m_refreshToken = root.value("refresh_token").toString();
    m_username = user.value("username").toString();

    if (m_accessToken.isEmpty() || m_refreshToken.isEmpty()) {
        emit authError("Auth service did not return tokens.");
        return;
    }

    if (operation == "register") {
        emit registrationSucceeded(
            m_username,
            m_accessToken,
            m_refreshToken);
    } else {
        emit loginSucceeded(
            m_username,
            m_accessToken,
            m_refreshToken);
    }
}
