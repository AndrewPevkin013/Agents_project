#pragma once

#include <QObject>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QStringList>

class QNetworkRequest;

class ApiClient final : public QObject
{
    Q_OBJECT

public:
    explicit ApiClient(QObject *parent = nullptr);

    void setBaseUrl(const QString &url);
    [[nodiscard]] QString baseUrl() const;
    void setAccessToken(const QString &token);
    [[nodiscard]] QString accessToken() const;

    void getAgents();
    void sendHandlerRequest(const QString &request);
    void runAgent(const QString &agentName, const QString &prompt);

    void createAgent(
        const QString &name,
        const QString &modelName,
        const QString &systemPrompt,
        const QStringList &tags);

    void deleteAgent(const QString &agentName);

    void uploadDocument(const QString &filePath);
    void routeDocument(const QString &filePath, const QString &documentText);

    void resolveLogger();
    void getMetrics();
    void getSystemState();

signals:
    void responseReady(const QString &title, const QJsonObject &json);
    void errorOccurred(const QString &message);

private:
    QString m_baseUrl = "http://127.0.0.1:8000";
    QString m_accessToken;
    QNetworkAccessManager m_network;

    void get(const QString &path, const QString &title);
    void postJson(const QString &path, const QJsonObject &body, const QString &title);
    void deleteRequest(const QString &path, const QString &title);
    void applyAuthorization(QNetworkRequest &request) const;
    void emitJsonResponse(
        const QString &title,
        const QByteArray &data,
        const QString &networkError = {});
};
