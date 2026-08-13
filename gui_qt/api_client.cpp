#include "api_client.h"

#include <QFile>
#include <QFileInfo>
#include <QHttpMultiPart>
#include <QHttpPart>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrl>

ApiClient::ApiClient(QObject *parent)
    : QObject(parent)
{
}

void ApiClient::setBaseUrl(const QString &url)
{
    m_baseUrl = url.trimmed();

    while (m_baseUrl.endsWith('/')) {
        m_baseUrl.chop(1);
    }
}

QString ApiClient::baseUrl() const
{
    return m_baseUrl;
}

void ApiClient::emitJsonResponse(
    const QString &title,
    const QByteArray &data,
    const QString &networkError)
{
    if (!networkError.isEmpty()) {
        emit errorOccurred(networkError + "\n" + QString::fromUtf8(data));
        return;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(data, &parseError);

    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        emit errorOccurred(
            "Server returned invalid JSON: " + parseError.errorString()
            + "\n" + QString::fromUtf8(data));
        return;
    }

    emit responseReady(title, document.object());
}

void ApiClient::get(const QString &path, const QString &title)
{
    QNetworkRequest request(QUrl(m_baseUrl + path));
    QNetworkReply *reply = m_network.get(request);

    connect(reply, &QNetworkReply::finished, this, [this, reply, title]() {
        const QByteArray data = reply->readAll();
        const QString error = reply->error() == QNetworkReply::NoError
            ? QString()
            : reply->errorString();

        emitJsonResponse(title, data, error);
        reply->deleteLater();
    });
}

void ApiClient::postJson(
    const QString &path,
    const QJsonObject &body,
    const QString &title)
{
    QNetworkRequest request(QUrl(m_baseUrl + path));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    QNetworkReply *reply =
        m_network.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact));

    connect(reply, &QNetworkReply::finished, this, [this, reply, title]() {
        const QByteArray data = reply->readAll();
        const QString error = reply->error() == QNetworkReply::NoError
            ? QString()
            : reply->errorString();

        emitJsonResponse(title, data, error);
        reply->deleteLater();
    });
}

void ApiClient::deleteRequest(const QString &path, const QString &title)
{
    QNetworkRequest request(QUrl(m_baseUrl + path));
    QNetworkReply *reply = m_network.deleteResource(request);

    connect(reply, &QNetworkReply::finished, this, [this, reply, title]() {
        const QByteArray data = reply->readAll();
        const QString error = reply->error() == QNetworkReply::NoError
            ? QString()
            : reply->errorString();

        emitJsonResponse(title, data, error);
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
        "/agents/" + QUrl::toPercentEncoding(agentName) + "/run",
        {{"prompt", prompt}},
        "Run Agent");
}

void ApiClient::createAgent(
    const QString &name,
    const QString &type,
    const QString &modelName,
    const QString &systemPrompt,
    const QStringList &tags)
{
    QJsonArray tagArray;
    for (const QString &tag : tags) {
        const QString value = tag.trimmed();
        if (!value.isEmpty()) {
            tagArray.append(value);
        }
    }

    const QJsonObject body{
        {"name", name.trimmed()},
        {"type", type.trimmed()},
        {"model_name", modelName.trimmed()},
        {"description", systemPrompt.trimmed()},
        {"system_prompt", systemPrompt.trimmed()},
        {"tags", tagArray}
    };

    postJson("/agents", body, "Create Agent");
}

void ApiClient::deleteAgent(const QString &agentName)
{
    deleteRequest(
        "/agents/" + QString::fromUtf8(QUrl::toPercentEncoding(agentName)),
        "Delete Agent");
}

void ApiClient::routeDocument(
    const QString &filePath,
    const QString &documentText)
{
    postJson(
        "/documents/route",
        {
            {"file_path", filePath},
            {"document_text", documentText},
            {"threshold", 1}
        },
        "Route Document");
}

void ApiClient::uploadDocument(const QString &filePath)
{
    auto *multiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    const QFileInfo info(filePath);

    auto *file = new QFile(filePath);
    if (!file->open(QIODevice::ReadOnly)) {
        emit errorOccurred("Cannot open file: " + filePath);
        delete file;
        delete multiPart;
        return;
    }

    QHttpPart filePart;
    filePart.setHeader(
        QNetworkRequest::ContentDispositionHeader,
        QVariant(
            QString("form-data; name=\"file\"; filename=\"%1\"")
                .arg(info.fileName())));
    filePart.setBodyDevice(file);

    file->setParent(multiPart);
    multiPart->append(filePart);

    QNetworkRequest request(QUrl(m_baseUrl + "/documents/upload"));
    QNetworkReply *reply = m_network.post(request, multiPart);
    multiPart->setParent(reply);

    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        const QByteArray data = reply->readAll();
        const QString error = reply->error() == QNetworkReply::NoError
            ? QString()
            : reply->errorString();

        emitJsonResponse("Upload Document", data, error);
        reply->deleteLater();
    });
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
