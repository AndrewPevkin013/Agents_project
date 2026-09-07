#pragma once

#include <QObject>
#include <QNetworkAccessManager>
#include <QJsonObject>

class ApiClient : public QObject
{
    Q_OBJECT

public:
    explicit ApiClient(QObject *parent = nullptr);

    void setBaseUrl(const QString &url);
    QString baseUrl() const;
    void uploadDocument(const QString &filePath);
    void getAgents();
    void sendHandlerRequest(const QString &request);
    void runAgent(const QString &agentName, const QString &prompt);
    void createAgent(
        const QString &name,
        const QString &type,
        const QString &modelName,
        const QString &systemPrompt,
        const QStringList &tags
        );
    void deleteAgent(const QString &agentName);
    void routeDocument(const QString &filePath, const QString &documentText);
    void resolveLogger();
    void getMetrics();
    void getSystemState();

signals:
    void responseReady(const QString &title, const QJsonObject &json);
    void errorOccurred(const QString &message);

private:
    QString m_baseUrl = "http://127.0.0.1:8000";
    QNetworkAccessManager m_network;

    void get(const QString &path, const QString &title);
    void postJson(const QString &path, const QJsonObject &body, const QString &title);
    void deleteRequest(const QString &path, const QString &title);
};
