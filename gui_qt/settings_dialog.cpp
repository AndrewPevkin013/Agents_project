#include "settings_dialog.h"

#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QTabWidget>
#include <QVBoxLayout>

#include "api_client.h"

SettingsDialog::SettingsDialog(ApiClient *api, QWidget *parent)
    : QDialog(parent)
    , m_api(api)
{
    setWindowTitle("Settings");
    setModal(true);
    resize(650, 560);
    buildInterface();
}

void SettingsDialog::buildInterface()
{
    setStyleSheet(R"(
        QDialog {
            background: #0c0c10;
            color: #eeeeef;
        }
        QTabWidget::pane {
            border: 1px solid #302327;
            border-radius: 10px;
            background: #111116;
        }
        QTabBar::tab {
            min-width: 120px;
            padding: 10px 16px;
            color: #aaaab2;
            background: #15151b;
            border: 1px solid #29292f;
        }
        QTabBar::tab:selected {
            color: white;
            background: #55151b;
            border-bottom: 2px solid #c63a45;
        }
        QLabel {
            color: #d5d5d8;
        }
        QLineEdit, QPlainTextEdit, QComboBox {
            color: #f2f2f3;
            background: #19191f;
            border: 1px solid #34343b;
            border-radius: 8px;
            padding: 9px;
            selection-background-color: #8c2731;
        }
        QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
            border: 1px solid #a8323d;
        }
        QPushButton {
            min-height: 36px;
            color: #eeeeef;
            background: #24242b;
            border: 1px solid #383840;
            border-radius: 8px;
            padding: 0 16px;
        }
        QPushButton:hover {
            background: #342126;
            border-color: #7b2b34;
        }
        QPushButton#primaryButton {
            background: #8d222d;
            border-color: #b53642;
        }
        QPushButton#primaryButton:hover {
            background: #a52b37;
        }
        QPushButton#dangerButton {
            background: #451419;
            border-color: #7c252d;
        }
    )");

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(18, 18, 18, 18);
    root->setSpacing(14);

    auto *title = new QLabel("Application settings", this);
    title->setStyleSheet("font-size: 21px; font-weight: 700; color: white;");
    root->addWidget(title);

    auto *tabs = new QTabWidget(this);

    auto *serverPage = new QWidget(tabs);
    auto *serverLayout = new QVBoxLayout(serverPage);
    auto *serverForm = new QFormLayout();

    m_serverUrl = new QLineEdit(m_api->baseUrl(), serverPage);
    serverForm->addRow("Server URL:", m_serverUrl);

    auto *applyButton = new QPushButton("Apply server address", serverPage);
    applyButton->setObjectName("primaryButton");

    serverLayout->addLayout(serverForm);
    serverLayout->addWidget(applyButton);
    serverLayout->addStretch();

    connect(applyButton, &QPushButton::clicked,
            this, &SettingsDialog::applyServerUrl);

    tabs->addTab(serverPage, "Connection");

    auto *agentPage = new QWidget(tabs);
    auto *agentLayout = new QVBoxLayout(agentPage);
    auto *agentForm = new QFormLayout();

    m_agentName = new QLineEdit(agentPage);
    m_agentName->setPlaceholderText("DevOpsAgent");

    m_modelName = new QLineEdit(agentPage);
    m_modelName->setPlaceholderText("Qwen2.5-3B-Instruct");

    m_agentTags = new QLineEdit(agentPage);
    m_agentTags->setPlaceholderText("devops, docker, deploy");

    m_agentPrompt = new QPlainTextEdit(agentPage);
    m_agentPrompt->setPlaceholderText(
        "Ты DevOps-агент. Отвечаешь за инфраструктуру, Docker и CI/CD.");
    m_agentPrompt->setMinimumHeight(150);

    agentForm->addRow("Name:", m_agentName);
    agentForm->addRow("Model folder:", m_modelName);
    agentForm->addRow("Tags:", m_agentTags);
    agentForm->addRow("System prompt:", m_agentPrompt);

    auto *agentButtons = new QHBoxLayout();
    auto *createButton = new QPushButton("Create / update agent", agentPage);
    auto *deleteButton = new QPushButton("Delete agent", agentPage);
    createButton->setObjectName("primaryButton");
    deleteButton->setObjectName("dangerButton");

    agentButtons->addWidget(createButton);
    agentButtons->addWidget(deleteButton);

    agentLayout->addLayout(agentForm);
    agentLayout->addLayout(agentButtons);

    connect(createButton, &QPushButton::clicked,
            this, &SettingsDialog::createAgent);
    connect(deleteButton, &QPushButton::clicked,
            this, &SettingsDialog::deleteAgent);

    tabs->addTab(agentPage, "Agents");

    auto *systemPage = new QWidget(tabs);
    auto *systemLayout = new QVBoxLayout(systemPage);

    auto *metricsButton = new QPushButton("Request runtime metrics", systemPage);
    auto *stateButton = new QPushButton("Request system state", systemPage);
    auto *loggerButton = new QPushButton("Resolve Logger conflicts", systemPage);

    systemLayout->addWidget(metricsButton);
    systemLayout->addWidget(stateButton);
    systemLayout->addWidget(loggerButton);
    systemLayout->addStretch();

    connect(metricsButton, &QPushButton::clicked,
            m_api, &ApiClient::getMetrics);
    connect(stateButton, &QPushButton::clicked,
            m_api, &ApiClient::getSystemState);
    connect(loggerButton, &QPushButton::clicked,
            m_api, &ApiClient::resolveLogger);

    tabs->addTab(systemPage, "System");

    root->addWidget(tabs);

    auto *closeButton = new QPushButton("Close", this);
    connect(closeButton, &QPushButton::clicked, this, &QDialog::accept);
    root->addWidget(closeButton, 0, Qt::AlignRight);
}

void SettingsDialog::applyServerUrl()
{
    m_api->setBaseUrl(m_serverUrl->text());
}

void SettingsDialog::createAgent()
{
    m_api->createAgent(
        m_agentName->text(),
        m_modelName->text(),
        m_agentPrompt->toPlainText(),
        m_agentTags->text().split(',', Qt::SkipEmptyParts));
}

void SettingsDialog::deleteAgent()
{
    const QString name = m_agentName->text().trimmed();
    if (!name.isEmpty()) {
        m_api->deleteAgent(name);
    }
}
