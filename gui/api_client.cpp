#include "api_client.h"

#include <QNetworkRequest>
#include <QNetworkReply>
#include <QJsonDocument>
#include <QJsonArray>
#include <QUrl>
#include <QHttpMultiPart>
#include <QHttpPart>
#include <QFile>
#include <QFileInfo>

ApiClient::ApiClient(QObject *parent)
    : QObject(parent)
{
}

void ApiClient::setBaseUrl(const QString &url)
{
    m_baseUrl = url;
    if (m_baseUrl.endsWith('/')) {
        m_baseUrl.chop(1);
    }
}

QString ApiClient::baseUrl() const
{
    return m_baseUrl;
}

void ApiClient::get(const QString &path, const QString &title)
{
    QNetworkRequest request(QUrl(m_baseUrl + path));
    QNetworkReply *reply = m_network.get(request);

    connect(reply, &QNetworkReply::finished, this, [this, reply, title]() {
        const QByteArray data = reply->readAll();

        if (reply->error() != QNetworkReply::NoError) {
            emit errorOccurred(reply->errorString() + "\n" + QString::fromUtf8(data));
            reply->deleteLater();
            return;
        }

        const QJsonDocument doc = QJsonDocument::fromJson(data);
        emit responseReady(title, doc.object());

        reply->deleteLater();
    });
}

void ApiClient::postJson(const QString &path, const QJsonObject &body, const QString &title)
{
    QNetworkRequest request(QUrl(m_baseUrl + path));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    const QByteArray payload = QJsonDocument(body).toJson();

    QNetworkReply *reply = m_network.post(request, payload);

    connect(reply, &QNetworkReply::finished, this, [this, reply, title]() {
        const QByteArray data = reply->readAll();

        if (reply->error() != QNetworkReply::NoError) {
            emit errorOccurred(reply->errorString() + "\n" + QString::fromUtf8(data));
            reply->deleteLater();
            return;
        }

        const QJsonDocument doc = QJsonDocument::fromJson(data);
        emit responseReady(title, doc.object());

        reply->deleteLater();
    });
}

void ApiClient::deleteRequest(const QString &path, const QString &title)
{
    QNetworkRequest request(QUrl(m_baseUrl + path));
    QNetworkReply *reply = m_network.deleteResource(request);

    connect(reply, &QNetworkReply::finished, this, [this, reply, title]() {
        const QByteArray data = reply->readAll();

        if (reply->error() != QNetworkReply::NoError) {
            emit errorOccurred(reply->errorString() + "\n" + QString::fromUtf8(data));
            reply->deleteLater();
            return;
        }

        const QJsonDocument doc = QJsonDocument::fromJson(data);
        emit responseReady(title, doc.object());

        reply->deleteLater();
    });
}

void ApiClient::getAgents()
{
    get("/agents", "Agents");
}

void ApiClient::sendHandlerRequest(const QString &request)
{
    postJson("/handler", {{"request", request}}, "Handler");
}

void ApiClient::runAgent(const QString &agentName, const QString &prompt)
{
    postJson(
        "/agents/" + agentName + "/run",
        {{"prompt", prompt}},
        "Run Agent"
        );
}

void ApiClient::createAgent(
    const QString &name,
    const QString &type,
    const QString &modelName,
    const QString &systemPrompt,
    const QStringList &tags
    )
{
    QJsonArray tagArray;
    for (const QString &tag : tags) {
        tagArray.append(tag.trimmed());
    }

    QJsonObject body {
        {"name", name},
        {"type", type},
        {"model_name", modelName},
        {"description", systemPrompt},
        {"system_prompt", systemPrompt},
        {"tags", tagArray}
    };

    postJson("/agents", body, "Create Agent");
}

void ApiClient::deleteAgent(const QString &agentName)
{
    deleteRequest("/agents/" + agentName, "Delete Agent");
}

void ApiClient::routeDocument(const QString &filePath, const QString &documentText)
{
    postJson(
        "/documents/route",
        {
            {"file_path", filePath},
            {"document_text", documentText},
            {"threshold", 1}
        },
        "Route Document"
        );
}

void ApiClient::resolveLogger()
{
    postJson("/logger/resolve", {}, "Logger");
}

void ApiClient::getMetrics()
{
    get("/logs/metrics", "Metrics");
}

void ApiClient::getSystemState()
{
    get("/logs/state", "System State");
}

void ApiClient::uploadDocument(const QString &filePath)
{
    auto *multiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);

    QFileInfo info(filePath);

    QHttpPart filePart;
    filePart.setHeader(
        QNetworkRequest::ContentDispositionHeader,
        QVariant(QString("form-data; name=\"file\"; filename=\"%1\"").arg(info.fileName()))
    );

    auto *file = new QFile(filePath);
    if (!file->open(QIODevice::ReadOnly)) {
        emit errorOccurred("Cannot open file: " + filePath);
        delete file;
        delete multiPart;
        return;
    }

    filePart.setBodyDevice(file);
    file->setParent(multiPart);
    multiPart->append(filePart);

    QNetworkRequest request(QUrl(m_baseUrl + "/documents/upload"));
    QNetworkReply *reply = m_network.post(request, multiPart);
    multiPart->setParent(reply);

    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        const QByteArray data = reply->readAll();

        if (reply->error() != QNetworkReply::NoError) {
            emit errorOccurred(reply->errorString() + "\n" + QString::fromUtf8(data));
            reply->deleteLater();
            return;
        }

        const QJsonDocument doc = QJsonDocument::fromJson(data);
        emit responseReady("Upload Document", doc.object());

        reply->deleteLater();
    });
}
