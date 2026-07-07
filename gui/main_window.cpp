#include "main_window.h"

#include <QTabWidget>
#include <QVBoxLayout>
#include <QFormLayout>
#include <QLabel>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QJsonValue>
#include <QMessageBox>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QMimeData>
#include <QUrl>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setWindowTitle("Multi-Agent Desktop Client");
    setAcceptDrops(true);

    auto *tabs = new QTabWidget(this);
    tabs->addTab(createServerPanel(), "Server");
    tabs->addTab(createHandlerPanel(), "Handler Chat");
    tabs->addTab(createAgentsPanel(), "Agents");
    tabs->addTab(createDocumentsPanel(), "Documents");
    tabs->addTab(createLogsPanel(), "Logs");

    m_output = new QPlainTextEdit(this);
    m_output->setReadOnly(true);
    m_output->setMinimumHeight(260);

    auto *root = new QWidget(this);
    auto *layout = new QVBoxLayout(root);

    layout->addWidget(tabs);
    layout->addWidget(new QLabel("Response:"));
    layout->addWidget(m_output);

    setCentralWidget(root);

    connect(&m_api, &ApiClient::responseReady, this, &MainWindow::printJson);
    connect(&m_api, &ApiClient::errorOccurred, this, &MainWindow::printError);

    m_handlerTimeout = new QTimer(this);
    m_handlerTimeout->setSingleShot(true);

    connect(m_handlerTimeout, &QTimer::timeout, this, [this]() {
        unlockHandler();
        m_output->appendPlainText("=== HANDLER TIMEOUT ===");
        m_output->appendPlainText("Сервер не ответил за 60 секунд.");
    });
}

QWidget *MainWindow::createServerPanel()
{
    auto *widget = new QWidget(this);
    auto *layout = new QVBoxLayout(widget);

    m_serverUrl = new QLineEdit("http://127.0.0.1:8000", widget);

    auto *applyButton = new QPushButton("Apply server URL", widget);
    auto *agentsButton = new QPushButton("Test: GET /agents", widget);
    auto *metricsButton = new QPushButton("Test: GET /logs/metrics", widget);

    layout->addWidget(new QLabel("Server URL:"));
    layout->addWidget(m_serverUrl);
    layout->addWidget(applyButton);
    layout->addWidget(agentsButton);
    layout->addWidget(metricsButton);
    layout->addStretch();

    connect(applyButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        QMessageBox::information(this, "Server", "Server URL applied");
    });

    connect(agentsButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.getAgents();
    });

    connect(metricsButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.getMetrics();
    });

    return widget;
}

QWidget *MainWindow::createHandlerPanel()
{
    auto *widget = new QWidget(this);
    auto *layout = new QVBoxLayout(widget);

    m_handlerInput = new QPlainTextEdit(widget);
    m_handlerInput->setPlaceholderText(
        "Например: Выполни command mode: создай агента AnalystAgent..."
        );

    m_handlerSendButton = new QPushButton("Send to Handler", widget);

    layout->addWidget(new QLabel("Handler request:"));
    layout->addWidget(m_handlerInput);
    layout->addWidget(m_handlerSendButton);

    connect(m_handlerSendButton, &QPushButton::clicked, this, [this]() {
        if (m_handlerBusy) {
            return;
        }

        const QString requestText = m_handlerInput->toPlainText().trimmed();

        if (requestText.isEmpty()) {
            return;
        }

        m_handlerBusy = true;
        m_handlerSendButton->setEnabled(false);

        m_output->appendPlainText("=== USER ===");
        m_output->appendPlainText(requestText);

        m_handlerInput->clear();

        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.sendHandlerRequest(requestText);

        m_handlerTimeout->start(60000);
    });

    return widget;
}

QWidget *MainWindow::createAgentsPanel()
{
    auto *widget = new QWidget(this);
    auto *layout = new QVBoxLayout(widget);

    m_agentsList = new QListWidget(widget);
    m_currentAgentLabel = new QLabel("Selected agent: none", widget);

    layout->addWidget(new QLabel("Available agents:"));
    layout->addWidget(m_agentsList);
    layout->addWidget(m_currentAgentLabel);

    auto *form = new QFormLayout();

    m_agentName = new QLineEdit(widget);
    m_agentName->setPlaceholderText("AnalystAgent");

    m_agentType = new QComboBox(widget);
    m_agentType->addItems({"mock", "llm"});

    m_modelName = new QLineEdit(widget);
    m_modelName->setPlaceholderText("Qwen2.5-3B-Instruct");

    m_agentTags = new QLineEdit(widget);
    m_agentTags->setPlaceholderText("analysis, summary");

    m_agentPrompt = new QPlainTextEdit(widget);
    m_agentPrompt->setPlaceholderText("Ты аналитический агент...");

    form->addRow("Name:", m_agentName);
    form->addRow("Type:", m_agentType);
    form->addRow("Model:", m_modelName);
    form->addRow("Tags:", m_agentTags);
    form->addRow("System prompt:", m_agentPrompt);

    auto *createButton = new QPushButton("Create agent", widget);
    auto *refreshButton = new QPushButton("Refresh agents", widget);
    auto *deleteButton = new QPushButton("Delete selected/name", widget);

    m_runAgentName = new QLineEdit(widget);
    m_runAgentName->setPlaceholderText("AnalystAgent");

    m_runPrompt = new QPlainTextEdit(widget);
    m_runPrompt->setPlaceholderText("Объясни архитектуру проекта");

    auto *runButton = new QPushButton("Run selected agent", widget);

    layout->addLayout(form);
    layout->addWidget(createButton);
    layout->addWidget(refreshButton);
    layout->addWidget(deleteButton);
    layout->addSpacing(16);
    layout->addWidget(new QLabel("Chat with selected agent:"));
    layout->addWidget(m_runAgentName);
    layout->addWidget(m_runPrompt);
    layout->addWidget(runButton);

    connect(m_agentsList, &QListWidget::itemClicked, this, [this](QListWidgetItem *item) {
        m_currentAgent = item->text();
        m_runAgentName->setText(m_currentAgent);
        m_agentName->setText(m_currentAgent);
        m_currentAgentLabel->setText("Selected agent: " + m_currentAgent);
    });

    connect(createButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());

        const QStringList tags = m_agentTags->text().split(",", Qt::SkipEmptyParts);

        m_api.createAgent(
            m_agentName->text().trimmed(),
            m_agentType->currentText(),
            m_modelName->text().trimmed(),
            m_agentPrompt->toPlainText().trimmed(),
            tags
            );
    });

    connect(refreshButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.getAgents();
    });

    connect(deleteButton, &QPushButton::clicked, this, [this]() {
        const QString name = m_agentName->text().trimmed();
        if (name.isEmpty()) {
            return;
        }

        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.deleteAgent(name);
    });

    connect(runButton, &QPushButton::clicked, this, [this]() {
        const QString agentName = m_runAgentName->text().trimmed();
        const QString prompt = m_runPrompt->toPlainText().trimmed();

        if (agentName.isEmpty() || prompt.isEmpty()) {
            return;
        }

        m_output->appendPlainText("=== USER TO " + agentName + " ===");
        m_output->appendPlainText(prompt);

        m_runPrompt->clear();

        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.runAgent(agentName, prompt);
    });

    return widget;
}

QWidget *MainWindow::createDocumentsPanel()
{
    auto *widget = new QWidget(this);
    auto *layout = new QVBoxLayout(widget);

    m_docPath = new QLineEdit(widget);
    m_docPath->setPlaceholderText("Перетащи файл в окно или укажи путь на сервере");

    m_docText = new QPlainTextEdit(widget);
    m_docText->setPlaceholderText("Текст документа, если файла нет на сервере");

    auto *routeButton = new QPushButton("Route document by server-side path", widget);

    layout->addWidget(new QLabel("Document path:"));
    layout->addWidget(m_docPath);
    layout->addWidget(new QLabel("Document text:"));
    layout->addWidget(m_docText);
    layout->addWidget(routeButton);
    layout->addStretch();

    connect(routeButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.routeDocument(
            m_docPath->text().trimmed(),
            m_docText->toPlainText().trimmed()
            );
    });

    return widget;
}

QWidget *MainWindow::createLogsPanel()
{
    auto *widget = new QWidget(this);
    auto *layout = new QVBoxLayout(widget);

    auto *metricsButton = new QPushButton("Get metrics", widget);
    auto *stateButton = new QPushButton("Save/Get system state", widget);
    auto *loggerButton = new QPushButton("Resolve logger conflicts", widget);

    layout->addWidget(metricsButton);
    layout->addWidget(stateButton);
    layout->addWidget(loggerButton);
    layout->addStretch();

    connect(metricsButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.getMetrics();
    });

    connect(stateButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.getSystemState();
    });

    connect(loggerButton, &QPushButton::clicked, this, [this]() {
        m_api.setBaseUrl(m_serverUrl->text().trimmed());
        m_api.resolveLogger();
    });

    return widget;
}

void MainWindow::updateAgentsList(const QJsonObject &json)
{
    if (!m_agentsList) {
        return;
    }

    m_agentsList->clear();

    const QJsonArray agents = json.value("agents").toArray();

    for (const QJsonValue &value : agents) {
        m_agentsList->addItem(value.toString());
    }
}

void MainWindow::unlockHandler()
{
    if (m_handlerTimeout) {
        m_handlerTimeout->stop();
    }

    m_handlerBusy = false;

    if (m_handlerSendButton) {
        m_handlerSendButton->setEnabled(true);
    }
}

void MainWindow::printJson(const QString &title, const QJsonObject &json)
{
    if (title == "Handler") {
        unlockHandler();
    }

    if (title == "Agents") {
        updateAgentsList(json);
    }

    if (title == "Create Agent" || title == "Delete Agent" || title == "Upload Document") {
        m_api.getAgents();
    }

    const QJsonDocument doc(json);

    m_output->appendPlainText("=== " + title + " ===");
    m_output->appendPlainText(QString::fromUtf8(doc.toJson(QJsonDocument::Indented)));
}

void MainWindow::printError(const QString &message)
{
    unlockHandler();

    m_output->appendPlainText("=== ERROR ===");
    m_output->appendPlainText(message);
}

void MainWindow::dragEnterEvent(QDragEnterEvent *event)
{
    if (event->mimeData()->hasUrls()) {
        event->acceptProposedAction();
    }
}

void MainWindow::dropEvent(QDropEvent *event)
{
    const QList<QUrl> urls = event->mimeData()->urls();

    for (const QUrl &url : urls) {
        const QString filePath = url.toLocalFile();

        if (!filePath.isEmpty()) {
            m_docPath->setText(filePath);

            m_output->appendPlainText("=== UPLOAD DOCUMENT ===");
            m_output->appendPlainText(filePath);

            m_api.setBaseUrl(m_serverUrl->text().trimmed());
            m_api.uploadDocument(filePath);
        }
    }

    event->acceptProposedAction();
}
